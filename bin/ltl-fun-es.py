import logging.config

import numpy as np
from pypet import Environment

from ltl import dict_to_list
from ltl.dataprocessing import get_skeleton_traj, get_var_from_runs, get_var_from_generations
from ltl.logging_tools import create_shared_logger_data, configure_loggers
from ltl.optimizees.functions import tools as function_tools
from ltl.optimizees.functions.benchmarked_functions import BenchmarkedFunctions
from ltl.optimizees.functions.optimizee import FunctionGeneratorOptimizee
from ltl.optimizers.evolutionstrategies import EvolutionStrategiesParameters, EvolutionStrategiesOptimizer
from ltl.paths import Paths
from ltl.recorder import Recorder

logger = logging.getLogger('bin.ltl-fun-es')


def run_experiment():
    name = 'LTL-FUN-ES'
    try:
        with open('bin/path.conf') as f:
            root_dir_path = f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError("You have not set the root path to store your results."
                                " Write the path to a path.conf text file in the bin directory"
                                " before running the simulation")

    trajectory_name = 'mirroring-and-fitness-shaping'

    paths = Paths(name, dict(run_num='test'), root_dir_path=root_dir_path, suffix="-" + trajectory_name)

    print("All output logs can be found in directory ", paths.logs_path)

    # Create an environment that handles running our simulation
    # This initializes a PyPet environment
    env = Environment(
        trajectory=trajectory_name,
        filename=paths.output_dir_path,
        file_title='{} data'.format(name),
        comment='{} data'.format(name),
        add_time=True,
        automatic_storing=True,
        log_stdout=False,  # Sends stdout to logs
    )
    create_shared_logger_data(
        logger_names=['bin', 'optimizers'],
        log_levels=['INFO', 'INFO'],
        log_to_consoles=[True, True],
        sim_name=name,
        log_directory=paths.logs_path)
    configure_loggers()

    # Get the trajectory from the environment
    traj = env.trajectory

    ## Benchmark function
    function_id = 14
    bench_functs = BenchmarkedFunctions()
    (benchmark_name, benchmark_function), benchmark_parameters = \
        bench_functs.get_function_by_index(function_id, noise=True)

    optimizee_seed = 200
    random_state = np.random.RandomState(seed=optimizee_seed)
    function_tools.plot(benchmark_function, random_state)

    ## Innerloop simulator
    optimizee = FunctionGeneratorOptimizee(traj, benchmark_function, seed=optimizee_seed)

    ## Outerloop optimizer initialization
    optimizer_seed = 1234
    parameters = EvolutionStrategiesParameters(
        learning_rate=0.1,
        noise_std=1.0,
        mirrored_sampling_enabled=True,
        fitness_shaping_enabled=True,
        pop_size=20,
        n_iteration=1000,
        stop_criterion=np.Inf,
        seed=optimizer_seed)

    optimizer = EvolutionStrategiesOptimizer(
        traj,
        optimizee_create_individual=optimizee.create_individual,
        optimizee_fitness_weights=(-1.,),
        parameters=parameters,
        optimizee_bounding_func=optimizee.bounding_func)

    # Add post processing
    env.add_postprocessing(optimizer.post_process)

    # Add Recorder
    recorder = Recorder(
        trajectory=traj,
        optimizee_name=benchmark_name,
        optimizee_parameters=benchmark_parameters,
        optimizer_name=optimizer.__class__.__name__,
        optimizer_parameters=optimizer.get_params())
    recorder.start()

    # Run the simulation with all parameter combinations
    env.run(optimizee.simulate)

    ## Outerloop optimizer end
    optimizer.end(traj)
    recorder.end()

    # Finally disable logging and close all log-files
    env.disable_logging()

    return traj.v_storage_service.filename, traj.v_name, paths


def process_results(filename, trajname, paths):
    # NOTE: This is written specifically for benchmark function number 14

    from ltl.matplotlib_ import plt

    traj = get_skeleton_traj(filename, trajname)

    fitness_list, run_id_list = get_var_from_runs(traj, 'results.fitness', with_ids=True, status_interval=200)
    algorithm_params_list = get_var_from_generations(traj, 'algorithm_params')

    best_fitness_list = [x['best_fitness_in_run'] for x in algorithm_params_list]
    average_fitness_list = [x['average_fitness_in_run'] for x in algorithm_params_list]
    generation_list = [x['generation'] for x in algorithm_params_list]
    current_individual_fitness = [x['current_individual_fitness'] for x in algorithm_params_list]

    pop_size_list = [params_dict['pop_size'] for params_dict in algorithm_params_list]

    pop_size_list_cumsum = np.cumsum(pop_size_list)
    gen_no_list = np.zeros_like(run_id_list)  # gen_no_list[i] = gen no of ith run
    gen_no_list[pop_size_list_cumsum[:-1]] = 1
    gen_no_list = np.cumsum(gen_no_list)

    # NOTE: This is because the value of the fitness weight is negative!!
    fitness_list = -1 * np.array(fitness_list)

    fig, ax = plt.subplots(figsize=(15, 7))
    ax.plot(gen_no_list, fitness_list, '.', label='fitness distribution')
    ax.plot(generation_list, current_individual_fitness, label='current individual fitness')
    ax.plot(generation_list, best_fitness_list, label='best fitness')
    ax.plot(generation_list, average_fitness_list, label='average fitness')
    ax.legend()
    ax.set_title("Testing", fontsize='small')
    fig.savefig(paths.get_fpath('fitness-v-generation', 'png'))

    individual_list, run_id_list = get_var_from_runs(traj, 'results.individual', with_ids=True, status_interval=200)

    individual_list_arr = [dict_to_list(ind) for ind in individual_list]

    xs = [p[0] for p in individual_list_arr]
    ys = [p[1] for p in individual_list_arr]

    fig, ax = plt.subplots(figsize=(15, 15))
    ax.scatter(xs, ys)
    # NOTE: -5, 5 'coz this is the range for benchmark function number 14
    ax.set(xlim=(-5, 5), ylim=(-5, 5))

    fig.savefig(paths.get_fpath('es-explored-points', 'png'))

    logger.info("Plots are in %s", paths.results_path)


def main():
    filename, trajname, paths = run_experiment()
    logger.info("Plotting now")
    process_results(filename, trajname, paths)


if __name__ == '__main__':
    main()