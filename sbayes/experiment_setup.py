#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" Setup of the Experiment"""
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Optional

from sbayes.util import set_experiment_name
from sbayes import config

try:
    import importlib.resources as pkg_resources     # PYTHON >= 3.7
except ImportError:
    import importlib_resources as pkg_resources     # PYTHON < 3.7

REQUIRED = '<REQUIRED>'
DEFAULT_CONFIG = json.loads(pkg_resources.read_text(config, 'default_config.json'))


class Experiment:

    """sBayes experiment class. Takes care of loading and verifying the config file,
    handling paths, setting up logging...

    Attributes:
        experiment_name (str): The name of the experiment run (= name of results folder)
        config_file (Path): The path to the config_file.
        config (dict): The config parsed into a python dictionary.
        base_directory (Path): The directory containing the config file.
        path_results (Path): The path to the results folder.
        logger (logging.Logger): The logger used throughout the run of the experiment.

    """

    def __init__(self,
                 experiment_name: str = "default",
                 config_file: Optional[Path] = None,
                 custom_settings: Optional[dict] = None,
                 log: bool = True):

        # Naming and shaming
        if experiment_name is None:
            self.experiment_name = set_experiment_name()
        else:
            self.experiment_name = experiment_name

        self.config_file = None
        self.config = {}
        self.base_directory = None
        self.path_results = None

        if config_file is not None:
            self.load_config(config_file, custom_settings=custom_settings)

        self.logger = self.init_logger()
        if log:
            self.log_experiment()

    def load_config(self,
                    config_file: Path,
                    custom_settings: Optional[dict] = None):

        # Get parameters from config_file
        self.base_directory, self.config_file = decompose_config_path(config_file)

        # Read the user specified config file
        with open(self.config_file, 'r') as f:
            self.config = json.load(f)

        set_defaults(self.config, DEFAULT_CONFIG)

        if custom_settings is not None:
            update_recursive(self.config, custom_settings)

        # Verify config
        self.verify_config()

        # Set results path

        self.path_results = '{path}/{experiment}/'.format(
            path=self.config['results']['path'],
            experiment=self.experiment_name
        )

        # Compile relative paths, to be relative to config file
        self.path_results = fix_relative_path(self.path_results, self.base_directory)

        if not os.path.exists(self.path_results):
            os.makedirs(self.path_results)

        self.add_logger_file(self.path_results)

    def is_simulation(self):
        return 'simulation' in self.config

    def verify_priors(self, priors_cfg: dict):

        # Define which priors are required
        required_priors = ['objects_per_cluster', 'geo', 'weights', "areal_effect", "confounding_effects"]

        # Check presence and validity of each required prior
        for key in required_priors:
            if key not in priors_cfg:
                NameError(f"Prior \'{key}\' is not defined in {self.config_file}.")

            prior = priors_cfg[key]

            # Cluster size
            if key == "objects_per_cluster":
                if 'type' not in prior:
                    raise NameError(f"`type` for prior \'{key}\' is not defined in {self.config_file}.")

            # Geo
            if key == "geo":
                if 'type' not in prior:
                    raise NameError(f"`type` for prior \'{key}\' is not defined in {self.config_file}.")

                if prior['type'] == "gaussian":
                    if 'covariance' not in prior:
                        raise NameError(
                            f"`covariance` for gaussian geo prior is not defined in {self.config_file}.")

                if prior['type'] == "cost_based":
                    if 'rate' not in prior:
                        raise NameError(
                            f"`rate` for cost based geo prior is not defined in {self.config_file}.")
                    if 'linkage' not in prior:
                        prior['linkage'] = "mst"
                    if 'costs' not in prior:
                        prior['costs'] = "from_data"
                    if prior['costs'] != "from_data":
                        prior['costs'] = fix_relative_path(prior['file'])

            # Weights
            if key == "weights":
                if 'type' not in prior:
                    raise NameError(f"`type` for prior \'{key}\' is not defined in {self.config_file}.")

            # Areal effects
            if key == "areal_effect":
                if 'type' not in prior:
                    raise NameError(f"`type` for prior \'{key}\' is not defined in {self.config_file}.")

            # Confounding effects
            if key == "confounding_effects":
                for k, v in self.config['model']['confounding_effects'].items():
                    if k not in self.config['model']['prior']['confounding_effects']:
                        raise NameError(f"Prior for \'{k}\' is not defined in {self.config_file}.")

                    for g in v:
                        if g not in self.config['model']['prior']['confounding_effects'][k]:
                            raise NameError(f"Prior for \'{g}\' is not defined in {self.config_file}.")

                        if 'type' not in self.config['model']['prior']['confounding_effects'][k][g]:
                            raise NameError(f"`type` for prior \'{g}\' is not defined in {self.config_file}.")

    def verify_config(self):
        # Check that all required fields are present
        for key, value, loc in iter_items_recursive(self.config):
            if value == REQUIRED:
                loc_string = ': '.join([f'"{k}"' for k in (loc + (key, REQUIRED))])
                raise NameError(f'The value for a required field is not defined in {self.config_file}:\n\t{loc_string}')\

        # Data
        if 'data' not in self.config:
            raise NameError(f'´data´ are not defined in {self.config_file}')

        # if not self.config['data']['simulated']:
        if not self.config['data']['features']:
            raise NameError("`features` is empty. Provide path to features file (e.g. features.csv)")
        else:
            self.config['data']['features'] = fix_relative_path(self.config['data']['features'], self.base_directory)

        if not self.config['data']['feature_states']:
            raise NameError("`feature_states` is empty. Provide path to feature_states file (e.g. feature_states.csv)")
        else:
            self.config['data']['feature_states'] = fix_relative_path(self.config['data']['feature_states'],
                                                                      self.base_directory)

        # Model / Priors
        self.verify_priors(self.config['model']['prior'])

        # MCMC
        if 'mcmc' not in self.config:
            NameError(f'´mcmc´ is not defined in {self.config_file}')

        # Tracer does not like unevenly spaced samples
        spacing = self.config['mcmc']['steps'] % self.config['mcmc']['samples']

        if spacing != 0.:
            raise ValueError("Non-consistent spacing between samples. Set ´steps´ to be a multiple of ´samples´.")

        # Do not use source operators if sampling from source is disabled
        if not self.config['model']['sample_source']:
            if self.config['mcmc']['operators'].get('source', 0) != 0:
                logging.warning('Operator for source was set to 0, because ´sample_source´ is disabled.')
            self.config['mcmc']['operators']['source'] = 0.0

        # Re-normalize weights for operators
        weights_sum = sum(self.config['mcmc']['operators'].values())

        for operator, weight in self.config['mcmc']['operators'].items():
            self.config['mcmc']['operators'][operator] = weight / weights_sum

        # Results
        # if 'simulated' not in self.config['data']:
        #     self.config['data']['simulated'] = False

    @staticmethod
    def init_logger():
        logger = logging.Logger('sbayesLogger', level=logging.DEBUG)
        logger.addHandler(logging.StreamHandler())
        return logger

    def add_logger_file(self, path_results):
        log_path = path_results / 'experiment.log'
        self.logger.addHandler(logging.FileHandler(filename=log_path))

    def log_experiment(self):
        self.logger.info("Experiment: %s", self.experiment_name)
        self.logger.info("File location for results: %s", self.path_results)


def decompose_config_path(config_path):
    abs_config_path = Path(config_path).absolute()
    base_directory = abs_config_path.parent
    return base_directory, abs_config_path


def fix_relative_path(path, base_directory):
    """Make sure that the provided path is either absolute or relative to the config file directory.
    Args:
        path (Path or str): The original path (absolute or relative).
        base_directory (str): The base directory
    Returns:
        Path: The fixed path."""

    path = Path(path)
    if path.is_absolute():
        return path
    else:
        return base_directory / path


def set_defaults(cfg: dict, default_cfg: dict):
    """Iterate through a recursive config dictionary and set all fields that are not
    present in cfg to the default values from default_cfg.

    == Usage ===
    >>> set_defaults(cfg={0:0, 1:{1:0}, 2:{2:1}},
    ...              default_cfg={1:{1:1}, 2:{1:1, 2:2}})
    {0: 0, 1: {1: 0}, 2: {2: 1, 1: 1}}
    >>> set_defaults(cfg={0:0, 1:1, 2:2},
    ...              default_cfg={1:{1:1}, 2:{1:1, 2:2}})
    {0: 0, 1: 1, 2: 2}
    """
    for key in default_cfg:
        if key not in cfg:
            # Field ´key´ is not defined in cfg -> use default
            cfg[key] = default_cfg[key]

        else:
            # Field ´key´ is defined in cfg
            # -> update recursively if the field is a dictionary
            if isinstance(default_cfg[key], dict) and isinstance(cfg[key], dict):
                set_defaults(cfg[key], default_cfg[key])

    return cfg


def update_recursive(cfg: dict, new_cfg: dict):
    """Iterate through a recursive config dictionary and update cfg in all fields that are specified in new_cfg.

    == Usage ===
    >>> update_recursive(cfg={0:0, 1:{1:0}, 2:{2:1}},
    ...                  new_cfg={1:{1:1}, 2:{1:1, 2:2}})
    {0: 0, 1: {1: 1}, 2: {2: 2, 1: 1}}
    >>> update_recursive(cfg={0:0, 1:1, 2:2},
    ...                  new_cfg={1:{1:1}, 2:{1:1, 2:2}})
    {0: 0, 1: {1: 1}, 2: {1: 1, 2: 2}}
    """
    for key in new_cfg:
        if (key in cfg) and isinstance(new_cfg[key], dict) and isinstance(cfg[key], dict):
            # Both dictionaries have another layer -> update recursively
            update_recursive(cfg[key], new_cfg[key])
        else:
            cfg[key] = new_cfg[key]

    return cfg


def iter_items_recursive(cfg: dict, loc=tuple()):
    """Recursively iterate through all key-value pairs in ´cfg´ and sub-dictionaries.

    Args:
        cfg (dict): Config dictionary, potentially containing sub-dictionaries.
        loc (tuple): Specifies the sequene of keys that lead to the current sub-dictionary.
    Yields:
        tuple: key-value pairs of the bottom level dictionaries

    == Usage ===
    >>> list(iter_items_recursive({0: 0, 1: {1: 0}, 2: {2: 1, 1: 1}}))
    [(0, 0, ()), (1, 0, (1,)), (2, 1, (2,)), (1, 1, (2,))]
    """
    for key, value in cfg.items():
        if isinstance(value, dict):
            yield from iter_items_recursive(value, loc + (key, ))
        else:
            yield key, value, loc


if __name__ == '__main__':
    import doctest
    doctest.testmod()
