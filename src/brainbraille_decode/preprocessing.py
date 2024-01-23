import numpy as np
from scipy.signal import butter, sosfilt
from sklearn.base import BaseEstimator, TransformerMixin
from joblib import Parallel, delayed


def flatten_fold(arr):
    return [e_i for run_i in arr for e_i in run_i]


def flatten_feature(arr):
    arr = np.array(arr)
    arr = arr.reshape((arr.shape[0], np.prod(arr.shape[1:])))
    return arr


class ButterworthBandpassFilter(BaseEstimator, TransformerMixin):
    def __init__(self, lowcut, highcut, fs, order=4, axis=0):
        self.sos = butter(
            order, [lowcut, highcut], analog=False, btype="band", output="sos", fs=fs
        )
        self.axis = axis

    def fit(self, X, y=None):
        return self

    def transform(self, X, y=None, axis=None):
        axis_to_use = self.axis if axis is None else axis
        return np.array(
            Parallel(n_jobs=-1)(
                delayed(sosfilt)(self.sos, x_i, axis_to_use) for x_i in X
            )
        )


class ZNormalizeByGroup(BaseEstimator, TransformerMixin):
    def __init__(self, train_group=None, test_group=None):
        self.train_group = np.array(train_group) if train_group is not None else None
        self.test_group = np.array(test_group) if test_group is not None else None
        self.z_norm_params_by_sub = {}
        self.default_mean = None
        self.default_std = None
        self.X = None

    def fit(self, X, y=None, train_group=None):
        if train_group is None:
            train_group = (
                self.train_group if self.train_group is not None else np.zeros(len(X))
            )

        X = np.array(X)
        self.X = X.copy()
        unique_train = np.unique(train_group)
        for sub_i in unique_train:
            sub_mask = self.train_group == sub_i
            X_sub = self.X[sub_mask, :]
            X_sub_mean = X_sub.mean(axis=(0, 1))
            X_sub_std = X_sub.std(axis=(0, 1))
            self.z_norm_params_by_sub[sub_i] = {"mean": X_sub_mean, "std": X_sub_std}
        return self

    def transform(self, X, test_group=None):
        X = np.array(X)
        fitted = False
        train_transform = False
        if self.X is not None:
            fitted = True
            if np.allclose(X.shape, self.X.shape):
                if np.allclose(X, self.X):
                    train_transform = True

        if fitted and train_transform:
            train_group = (
                self.train_group if self.train_group is not None else np.zeros(len(X))
            )
            unique_train_group = np.unique(train_group)
            for sub_i in unique_train_group:
                sub_mask = self.train_group == sub_i
                X_sub = X[sub_mask, :]
                X[sub_mask, :] = (
                    X_sub - self.z_norm_params_by_sub[sub_i]["mean"]
                ) / self.z_norm_params_by_sub[sub_i]["std"]
        else:
            if test_group is None:
                test_group = (
                    self.test_group if self.test_group is not None else np.zeros(len(X))
                )
            unique_test_group = np.unique(test_group)
            for sub_i in unique_test_group:
                sub_mask = self.test_group == sub_i
                X_sub = X[sub_mask, :]
                if sub_i in self.z_norm_params_by_sub:
                    X[sub_mask, :] = (
                        X_sub - self.z_norm_params_by_sub[sub_i]["mean"]
                    ) / self.z_norm_params_by_sub[sub_i]["std"]
        return X


class DataSlice(BaseEstimator, TransformerMixin):
    def __init__(
        self,
        extra_frame,
        delay_frame,
        event_len_frame,
        event_interval_frame,
        feature_mask=None,
        num_trans=0,
    ):
        self.extra_frame = extra_frame
        self.delay_frame = delay_frame
        self.event_len_frame = event_len_frame
        self.event_interval_frame = event_interval_frame
        self.num_trans = num_trans
        self.feature_mask = feature_mask

    def fit(self, X, y=None, num_trans=None):
        if (num_trans is None) or (num_trans <= 0):
            if (y is not None) and (self.num_trans <= 0):
                self.num_trans = len(y[0]) - 1
        else:
            self.num_trans = num_trans
        return self

    def transform(self, X):
        slice_indice_start = (
            np.arange(0, self.event_len_frame * self.num_trans, self.event_len_frame)
            + self.delay_frame
        )
        slice_indice_end = (
            slice_indice_start + self.event_len_frame * 2 + self.extra_frame
        )
        sliced_x = np.array(
            [
                [
                    x_i[start_i:end_i, :]
                    for start_i, end_i in zip(slice_indice_start, slice_indice_end)
                ]
                for x_i in X
            ]
        )
        if self.feature_mask is not None:
            sliced_x = sliced_x[:, :, self.feature_mask]
        return sliced_x


class DataTrimmer(BaseEstimator, TransformerMixin):
    def __init__(self, num_delay_frame, num_frame_per_label):
        self.num_delay_frame = num_delay_frame
        self.num_frame_per_label = num_frame_per_label
        self.num_frame_to_trim_at_end = 0

    def fit(self, X, y):
        self.num_frame_to_trim_at_end = int(
            np.mean(
                [
                    len(x_i)
                    - (len(y_i) * self.num_frame_per_label)
                    - self.num_delay_frame
                    for x_i, y_i in zip(X, y)
                ]
            )
        )
        return self

    def transform(self, X):
        return [
            x_i[self.num_delay_frame : len(x_i) - self.num_frame_to_trim_at_end, :]
            for x_i in X
        ]