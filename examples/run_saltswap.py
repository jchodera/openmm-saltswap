"""
    Example implementation of a simulation of a box of water where the number of counterions can fluctuate in a box of water using the semi-grand canonical ensemble.
"""
from datetime import datetime
from simtk import openmm, unit
from simtk.openmm import app
import sys
sys.path.append("../saltswap/")
import saltswap

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run an openmm simulation with salt exchange moves.")
    parser.add_argument('-i','--input',type=str,help="the filename of the PDB structure of the starting configuration",default="waterbox.pdb")
    parser.add_argument('-o','--out',type=str,help="the filename of the PDB structure of the starting configuration",default="output.pdb")
    parser.add_argument('-d','--data',type=str,help="the filename of the text file where the simulation data will be stored",default="data.txt")
    parser.add_argument('-u','--deltachem',type=float,help="the difference between the chemical potential in kJ/mol of water and salt, default=+650",default=650.0)
    parser.add_argument('-c','--cycles',type=int,help="the number of cycles between MD and MCMC salt-water swaps, default=100",default=200)
    parser.add_argument('-s','--steps',type=int,help="the number of MD steps per cycle, default=250000",default=250000)
    parser.add_argument('-a','--attempts',type=int,help="the number of salt-water swap moves attempted, default=100",default=100)
    parser.add_argument('-e','--equilibration',type=int,help="the number of equilibration steps, default=1000",default=1000)
    parser.add_argument("--gpu",action='store_true',help="whether the simulation will be run on a GPU, default=False",default=False)

    args = parser.parse_args()

# CONSTANTS
kB = unit.BOLTZMANN_CONSTANT_kB * unit.AVOGADRO_CONSTANT_NA
pressure = 1*unit.atmospheres
temperature = 300*unit.kelvin
delta_chem = args.deltachem*unit.kilojoule_per_mole

#Loading a premade water box:
pdb = app.PDBFile('waterbox.pdb')
forcefield = app.ForceField('tip3p.xml')
system = forcefield.createSystem(pdb.topology,nonbondedMethod=app.PME, nonbondedCutoff=1.0*unit.nanometer, constraints=app.HBonds)
integrator = openmm.LangevinIntegrator(temperature, 1/unit.picosecond, 0.002*unit.picoseconds)
system.addForce(openmm.MonteCarloBarostat(pressure, temperature, 25))

if args.gpu==False :
    simulation = app.Simulation(pdb.topology, system, integrator)
else :
    platform = Platform.getPlatformByName('CUDA')
    properties = {'CudaPrecision': 'mixed'}
    simulation = app.Simulation(pdb.topology, system, integrator, platform, properties)
simulation.context.setPositions(pdb.positions)

iterations = args.cycles          # Number of rounds of MD and constant salt moves
nsteps = args.steps               # Amount of MD steps per iteration. 250000 steps = 500 picoseconds
nattempts = args.attempts         # Number of identity exchanges for water and ions.

print "Initializing constant salt class"
mc_constant_salt = saltswap.SaltSwap(system=system,topology=pdb.topology,temperature=temperature,delta_chem=delta_chem,integrator=integrator,pressure=pressure,nattempts_per_update=nattempts, debug=False)

print "Minimizing energy..."
simulation.minimizeEnergy(maxIterations=25)

print "Quick equilibration..."
simulation.context.setVelocitiesToTemperature(temperature)
simulation.step(args.equilibration)
positions = simulation.context.getState(getPositions=True,enforcePeriodicBox=True).getPositions(asNumpy=True)

# Opening file to store simulation data
f = open(args.data, 'w')
s = "{:4} {:5} {:5} {:5} {:10} {:10}\n".format("Step","Nwats","Nsod","Nchl","Energy","Volume")
f.write(s)
# Open PDB file for writing.
pdbfile = open(args.out, 'w')
app.PDBFile.writeHeader(pdb.topology, file=pdbfile)
app.PDBFile.writeModel(simulation.topology, positions, file=pdbfile, modelIndex=0)

print "Running simulation..."
startTime = datetime.now()
for i in range(iterations):
    simulation.step(nsteps)
    mc_constant_salt.update(simulation.context,nattempts=nattempts)
    # Custom reporters: (simulations.reporters severely slows the simulations down)
    cnts = mc_constant_salt.getIdentityCounts()
    nrg = mc_constant_salt.getPotEnergy(simulation.context)
    dims = simulation.topology.getUnitCellDimensions()
    vol = dims[0]*dims[1]*dims[2]
    s = s = "{:4} {:5} {:5} {:5} {:20} {:20}\n".format(i,cnts[0],cnts[1],cnts[2],nrg,vol)
    f.write(s)
    positions = simulation.context.getState(getPositions=True,enforcePeriodicBox=True).getPositions(asNumpy=True)
    app.PDBFile.writeModel(simulation.topology, positions, file=pdbfile, modelIndex=i+1)
tm = datetime.now() - startTime

s = "\nFraction of moves accepted = {:4}\n".format(mc_constant_salt.getAcceptanceProbability())
f.write(s)
s = "Elapsed time in seconds = {:7}\n".format(tm.seconds)
f.write(s)