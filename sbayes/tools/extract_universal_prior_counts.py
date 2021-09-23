import numpy as np
from pathlib import Path
import json
import os
import argparse

import tkinter as tk
from tkinter import filedialog

from sbayes.util import read_features_from_csv
from sbayes.util import scale_counts


def zip_internal_external(names):
    return zip(names['internal'], names['external'])


def main(args):
    # CLI
    parser = argparse.ArgumentParser(description="Tool to extract parameters for an empirical universal prior from sBayes data files.")
    parser.add_argument("--data", nargs="?", type=Path, help="The input CSV file")
    parser.add_argument("--featureStates", nargs="?", type=Path, help="The feature states CSV file")
    parser.add_argument("--output", nargs="?", type=Path, help="The output JSON file")
    parser.add_argument("--c0", nargs="?", default=1.0, type=float, help="Concentration of the hyper-prior (1.0 is Uniform)")
    parser.add_argument("--scaleCounts", nargs="?", default=None, type=float, help="Concentration of the hyper-prior (1.0 is Uniform)")

    args = parser.parse_args(args)
    prior_data_file = args.data
    feature_states_file = args.featureStates
    output_file = args.output
    hyper_prior_concentration = args.c0
    max_counts = args.scaleCounts

    # GUI
    tk_started = False
    current_directory = '.'

    if prior_data_file is None:
        if not tk_started:
            tk.Tk().withdraw()
            tk_started = True

        # Ask the user for data file
        prior_data_file = filedialog.askopenfilename(
            title='Select the data file in CSV format.',
            initialdir=current_directory,
            filetypes=(('csv files', '*.csv'), ('all files', '*.*'))

        )
        current_directory = os.path.dirname(prior_data_file)

    if feature_states_file is None:
        if not tk_started:
            tk.Tk().withdraw()
            tk_started = True

        # Ask the user for feature states file
        feature_states_file = filedialog.askopenfilename(
            title='Select the feature_states file in CSV format.',
            initialdir=current_directory,
            filetypes=(('csv files', '*.csv'), ('all files', '*.*'))
        )
        current_directory = os.path.dirname(feature_states_file)

    if output_file is None:
        if not tk_started:
            tk.Tk().withdraw()
            tk_started = True

        # Ask the user for output directory
        output_file = filedialog.askopenfilename(
            title='Select the output file (for universal prior counts) in JSON format.',
            initialdir=current_directory,
            filetypes=(('json files', '*.json'), ('all files', '*.*'))
        )

    prior_data_file = Path(prior_data_file)
    feature_states_file = Path(feature_states_file)
    output_file = Path(output_file)

    _, _, features, feature_names, state_names, _, families, family_names, _ = read_features_from_csv(
        file=prior_data_file,
        feature_states_file=feature_states_file
    )

    counts = np.sum(features, axis=0)       # shape: (n_features, n_states)

    # Apply the scale_counts if provided
    if max_counts is not None:
        counts = scale_counts(counts, max_counts)

    counts_dict = {}
    for i_f, feature in zip_internal_external(feature_names):
        counts_dict[feature] = {}
        for i_s, state in enumerate(state_names['external'][i_f]):
            counts_dict[feature][state] = hyper_prior_concentration + counts[i_f, i_s]

    with open(output_file, 'w') as prior_file:
        json.dump(counts_dict, prior_file, indent=4)


if __name__ == '__main__':
    import sys
    main(sys.argv[1:])