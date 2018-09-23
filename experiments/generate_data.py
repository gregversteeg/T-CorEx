from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

from scipy.stats import multivariate_normal
from sklearn.datasets import make_spd_matrix

import numpy as np
import random
import pandas as pd
import sklearn.covariance as skcov
import pickle as pkl


def nglf_sufficient_params(nv, m, snr, min_std, max_std):
    """ Generate parameters for p(x,z) joint model.
    """
    # NOTE: as z_std doesn't matter, we will set it 1.
    x_std = np.random.uniform(min_std, max_std, size=(nv,))
    cor_signs = np.sign(np.random.normal(size=(nv,)))
    snrs = np.random.uniform(0, snr, size=(nv,))
    rhos = map(lambda s: np.sqrt(s / (s + 1.0)), snrs)
    cor = cor_signs * rhos
    par = [np.random.randint(0, m) for i in range(nv)]
    return x_std, cor, par


def nglf_matrix_from_params(x_std, cor, par):
    """ Construct the covariance matrix corresponding to an NGLF model.
    """
    nv = len(x_std)
    S = np.zeros((nv, nv))
    for i in range(nv):
        for j in range(nv):
            if par[i] != par[j]:
                continue
            if i == j:
                S[i][j] = x_std[i] ** 2
            else:
                S[i][j] = x_std[i] * cor[i] * x_std[j] * cor[j]
    return S


def sample_from_nglf(nv, m, x_std, cor, par, ns, from_matrix=True):
    """ Sample ns from an NGLF model.
    """
    if from_matrix:
        sigma = nglf_matrix_from_params(x_std, cor, par)
        myu = np.zeros((nv,))
        return np.random.multivariate_normal(myu, sigma, size=(ns,)), sigma
    else:
        # generates following the probabilistic graphical model
        def generate_single():
            z = np.random.normal(0.0, 1.0, size=(m,))
            x = np.zeros((nv,))
            for i in range(nv):
                cond_mean = cor[i] * x_std[i] * z[par[i]]
                cond_var = (x_std[i] ** 2) * (1 - cor[i] ** 2)
                x[i] = np.random.normal(cond_mean, np.sqrt(cond_var))
            return x
        data = np.array([generate_single() for i in range(ns)])
        return data, None


def generate_nglf(nv, m, ns, snr=5.0, min_std=0.25, max_std=4.0, shuffle=False, from_matrix=True):
    """ Generates data according to an NGLF model.

    :param nv:          Number of observed variables
    :param m:           Number of latent factors
    :param ns:          Number of samples
    :param snr:         Average signal to noise ratio (U[0, snr])
    :param min_std:     Minimum std of x_i
    :param max_std:     Maximum std of x_i
    :param shuffle:     Whether to shuffle to x_i's
    :param from_matrix: Whether to construct and return ground truth covariance matrices
    :return: (data, ground_truth_cov)
    """
    block_size = nv // m
    x_std, cor, par = nglf_sufficient_params(nv, m, snr, min_std, max_std)
    if not shuffle:
        par = [i // block_size for i in range(nv)]
    return sample_from_nglf(nv, m, x_std, cor, par, ns, from_matrix)


def generate_general(nv, m, ns, normalize=False, shuffle=False):
    """ Generate general data using make_spd_matrix() function.

    :param nv:        Number of observed variables
    :param m:         Number of latent factors
    :param ns:        Number of samples for each time step
    :param normalize: Whether to set Var[x] = 1
    :param shuffle:   Whether to shuffle to x_i's
    :return: (data, ground_truth_cov)
    """
    assert nv % m == 0
    b = nv // m  # block size

    sigma = np.zeros((nv, nv))
    for i in range(m):
        block_cov = make_spd_matrix(b)
        if normalize:
            std = np.sqrt(block_cov.diagonal()).reshape((b, 1))
            block_cov /= std
            block_cov /= std.T
        sigma[i * b:(i + 1) * b, i * b:(i + 1) * b] = block_cov

    if shuffle:
        perm = range(nv)
        random.shuffle(perm)
        sigma_perm = np.zeros((nv, nv))
        for i in range(nv):
            for j in range(nv):
                sigma_perm[i, j] = sigma[perm[i], perm[j]]
        sigma = sigma_perm

    return np.random.multivariate_normal(myu, sigma, size=(ns,)), sigma


def load_nglf_sudden_change(nv, m, nt, ns, snr=5.0, min_std=0.25, max_std=4.0, shuffle=False, from_matrix=True):
    """ Generate data for the synthetic experiment with sudden change.

    :param nv:          Number of observed variables
    :param m:           Number of latent factors
    :param nt:          Number of time steps
    :param ns:      Number of samples for each time step
    :param snr:         Average signal to noise ratio (U[0, snr])
    :param min_std:     Minimum std of x_i
    :param max_std:     Maximum std of x_i
    :param nglf:        Whether to use NGLF model
    :param shuffle:     Whether to shuffle to x_i's
    :param from_matrix: Whether to construct and return ground truth covariance matrices
                        Valid only when nglf=True
    :return: (train_data, val_data, test_data, ground_truth_covs)
    """
    # find segment lengths
    n_segments = 2
    segment_lens = [nt // n_segments for i in range(n_segments)]
    segment_lens[-1] += nt - sum(segment_lens)
    assert (sum(segment_lens) == nt)

    # generate data
    data = []
    ground_truth_covs = []
    for seg_id in range(n_segments):
        # make sure each time we generate the same nglf model
        random.seed(42 + seg_id)
        np.random.seed(42 + seg_id)
        # generate for the current segment
        cur_ns = segment_lens[seg_id] * ns
        cur_data, cur_sigma = generate_nglf(nv=nv, m=m, ns=cur_ns, snr=snr, min_std=min_std, max_std=max_std,
                                            shuffle=shuffle, from_matrix=from_matrix)
        cur_data = cur_data.reshape((segment_lens[seg_id], ns, nv))
        data += list(cur_data)
        ground_truth_covs += [cur_sigma] * segment_lens[seg_id]

    return data, ground_truth_covs


def load_nglf_smooth_change(nv, m, nt, ns, snr=5.0, min_std=0.25, max_std=4.0):
    """ Generates data for the synthetic experiment with smooth varying NGLF model.

    :param nv:      Number of observed variables
    :param m:       Number of latent factors
    :param nt:      Number of time steps
    :param ns:      Number of samples for each time step
    :param snr:     Average signal to noise ratio (U[0, snr])
    :param min_std: Minimum std of x_i
    :param max_std: Maximum std of x_i
    :return: (data, ground_truth_cov)
    """
    random.seed(42)
    np.random.seed(42)

    # find segment lengths and generate sets of sufficient parameters
    n_segments = 2
    segment_lens = [nt // n_segments for i in range(n_segments)]
    segment_lens[-1] += nt - sum(segment_lens)
    assert(sum(segment_lens) == nt)
    nglfs = [nglf_sufficient_params(nv, m, snr, min_std, max_std)
             for i in range(n_segments + 1)]

    # generate the data
    ground_truth = []
    data = np.zeros((nt, ns, nv))
    t = 0
    for seg_id in range(n_segments):
        x_std_1, cor_1, par_1 = nglfs[seg_id]
        x_std_2, cor_2, par_2 = nglfs[seg_id + 1]
        L = segment_lens[seg_id]

        # choose where to change the parent of each x_i
        change_points = [np.random.randint(1, L) for i in range(nv)]

        par = par_1
        for st in range(L):
            # change parents if needed
            for i in range(nv):
                if change_points[i] == st:
                    par[i] = par_2[i]

            # build new sufficient statistics
            alpha = np.float(st) / L
            x_std = (1 - alpha) * x_std_1 + alpha * x_std_2
            cor = (1 - alpha) * cor_1 + alpha * cor_2
            sigma = nglf_matrix_from_params(x_std, cor, par)

            # generate data for a single time step
            ground_truth.append(sigma)
            myu = np.zeros((nv,))
            data[t, :] = np.random.multivariate_normal(myu, sigma, size=(ns,))
            t += 1

    return data, ground_truth


# TODO: Rewrite load_stock_data functions
def load_stock_data(nt, nv, train_cnt, val_cnt, test_cnt, data_type='stock_day',
                    start_date='2000-01-01', end_date='2018-01-01', stride='one'):
    random.seed(42)
    np.random.seed(42)

    print("Loading stock data ...")
    if data_type == 'stock_week':
        with open('../data/EOD_week.pkl', 'rb') as f:
            df = pd.DataFrame(pkl.load(f))
    elif data_type == 'stock_day':
        with open('../data/EOD_day.pkl', 'rb') as f:
            df = pd.DataFrame(pkl.load(f))
    else:
        raise ValueError("Unrecognized value '{}' for data_type variable".format(data_type))
    df = df[df.index >= start_date]
    df = df[df.index <= end_date]

    # shuffle the columns
    cols = sorted(list(df.columns))
    random.shuffle(cols)
    df = df[cols]

    train_data = []
    val_data = []
    test_data = []

    window = train_cnt + val_cnt + test_cnt
    if stride == 'one':
        indices = range(window, len(df) - window)
    if stride == 'full':
        indices = range(window, len(df) - window, window + 1)
    assert len(indices) >= nt

    for i in indices:
        start = i - window
        end = i + window + 1
        perm = range(2 * window + 1)
        random.shuffle(perm)

        part = np.array(df[start:end])
        assert len(part) == 2 * window + 1

        train_data.append(part[perm[:train_cnt]])
        val_data.append(part[perm[train_cnt:train_cnt + val_cnt]])
        test_data.append(part[perm[-test_cnt:]])

    # take last nt time steps
    train_data = np.array(train_data[-nt:])
    val_data = np.array(val_data[-nt:])
    test_data = np.array(test_data[-nt:])

    # add small gaussian noise
    noise_var = 1e-5
    noise_myu = np.zeros((train_data.shape[-1],))
    noise_cov = np.diag([noise_var] * train_data.shape[-1])
    train_data += np.random.multivariate_normal(noise_myu, noise_cov, size=train_data.shape[:-1])
    val_data += np.random.multivariate_normal(noise_myu, noise_cov, size=val_data.shape[:-1])
    test_data += np.random.multivariate_normal(noise_myu, noise_cov, size=test_data.shape[:-1])

    # find valid variables
    valid_stocks = []
    for i in range(train_data.shape[-1]):
        ok = True
        for t in range(train_data.shape[0]):
            if np.var(train_data[t, :, i]) > 1e-2:
                ok = False
                break
        if ok:
            valid_stocks.append(i)

    # select nv valid variables
    print("\tremained {} variables".format(len(valid_stocks)))
    assert len(valid_stocks) >= nv
    valid_stocks = valid_stocks[:nv]
    train_data = train_data[:, :, valid_stocks]
    val_data = val_data[:, :, valid_stocks]
    test_data = test_data[:, :, valid_stocks]

    # scale the data (this is needed for T-GLASSO to work)
    coef = np.sqrt(np.var(train_data, axis=0).mean())
    train_data = train_data / coef
    val_data = val_data / coef
    test_data = test_data / coef

    print('Stock data is loaded:')
    print('\ttrain shape:', train_data.shape)
    print('\tval   shape:', val_data.shape)
    print('\ttest  shape:', test_data.shape)

    return train_data, val_data, test_data


