'''
Triangle class creates multiple actuarial triangles in an easy to manage class.
The API borrows heavily from pandas for the purpose of indexing,slicing, and
accessing individual triangles within the broader class.

The core data structure at the heart of the Triangle class is a 4D numpy array
with dimensions defined as:
    Dimension 0: represents key dimensions or the lowest grain(s) at which you
                 want to manage the triangle, e.g State, Company, etc. The
                 grain supports multiple key dimensions that will behave like a
                 pandas.multiIndex

    Dimension 1: represents value dimensions or numeric data to be represented
                 in each triangle, e.g. Paid, Incurred, etc.

    Dimension 2: represents the origin dimension which will be stored as a date
                 e.g. Accident Month, Report Year, Policy Quarter, etc.

    Dimension 3: represents the development dimension which will be store
                 e.g. Valuation Month, Valuation Year, Valuation Quarter, etc.

Dimensions 0 and 1 are accessed like a pandas Dataframe.  You can think about
the 4d structure as a 2D Dataframe where each element (row, col) is its own 2D
triangle. The most common operations in pandas are included and allows for
powerful manipulation. For example:

    my_triangle['incurred'] = my_triangle['paid'] + my_triangle['reserve']

This snippet would extend the values dimension of the my_triangle instance for
all key, origin and development dimensions.

'''
import pandas as pd
import numpy as np
import copy
from UtilityFunctions import (to_datetime, development_lag, get_grain,
                              cartesian_product)


class Triangle():
    def __init__(self, data=None, origin=None, development=None,
                 values=None, groupby=None):
        # Sanitize Inputs
        if groupby is None:
            groupby = ['Total']
            data_agg = data.groupby(origin+development).sum().reset_index()
            data_agg[groupby[0]] = 'Total'
        else:
            data_agg = data.groupby(origin+development+groupby) \
                           .sum().reset_index()
        values = [values] if type(values) is str else values
        origin = [origin] if type(origin) is str else origin
        development = [development] if type(values) is str else development

        # Convert origin/development to dates
        origin_date = to_datetime(data_agg, origin)
        self.origin_grain = get_grain(origin_date)
        development_date = to_datetime(data_agg, development)
        self.development_grain = get_grain(development_date)

        # Prep the data for 4D Triangle
        data_agg = self.get_axes(data_agg, groupby, values,
                                 origin_date, development_date)
        data_agg = pd.pivot_table(data_agg, index=groupby+['origin'],
                                  columns='development', values=values,
                                  aggfunc='sum')
        # Assign object properties
        self.kdims = np.array(data_agg.index.droplevel(-1).unique())
        self.odims = np.array(data_agg.index.levels[-1].unique())
        self.ddims = np.array(data_agg.columns.levels[-1].unique())
        self.vdims = np.array(data_agg.columns.levels[0].unique())
        self.valuation_date = development_date.max()
        self.groupby = groupby
        self.iloc = Triangle.Ilocation(self)
        self.loc = Triangle.Location(self)
        # Create 4D Triangle
        triangle = \
            np.array(data_agg).reshape(len(self.kdims), len(self.odims),
                                       len(self.vdims), len(self.ddims))
        triangle = np.swapaxes(triangle, 1, 2)
        # Set all 0s to NAN for nansafe ufunc arithmetic
        triangle[triangle == 0] = np.nan
        self.triangle = triangle

    # ---------------------------------------------------------------- #
    # ----------------------- Class Properties ----------------------- #
    # ---------------------------------------------------------------- #
    @property
    def shape(self):
        ''' Returns 4D triangle shape '''
        return self.triangle.shape

    @property
    def latest_diagonal(self):
        return self.get_latest_diagonal()

    @property
    def keys(self):
        return pd.DataFrame(list(self.kdims), columns=self.groupby)

    # ---------------------------------------------------------------- #
    # ---------------------- End User Methods ------------------------ #
    # ---------------------------------------------------------------- #
    def get_latest_diagonal(self):
        ''' Method to return the latest diagonal of the triangle.
        '''
        nan_tri = self.nan_triangle()
        diagonal = np.ones(nan_tri.shape).cumsum(axis=1)
        x = np.expand_dims(nan_tri.shape[1] -
                           np.sum(np.isnan(nan_tri), axis=1), axis=1)
        diagonal = diagonal == np.repeat(x, nan_tri.shape[1], axis=1)
        diagonal = self.expand_dims(diagonal)
        return np.nansum(diagonal*self.triangle, axis=3)

    def incr_to_cum(self, inplace=False):
        '''Method to convert an incremental triangle into a cumulative triangle.

            Arguments:
                inplace: bool
                    Set to True will update the instance data attribute inplace

            Returns:
                Updated instance of triangle accumulated along the origin
        '''

        if inplace:
            nan_tri = self.expand_dims(self.nan_triangle())
            self.triangle = np.nan_to_num(self.triangle).cumsum(axis=3)*nan_tri
            return self
        else:
            new_obj = copy.deepcopy(self)
            return new_obj.incr_to_cum(inplace=True)

    def grain(self, grain='', incremental=False, inplace=False):
        ''' TODO - Make incremental work '''
        if inplace:
            # First do Origin
            origin_grain = grain[1:2]
            development_grain = grain[-1]
            orig = np.nan_to_num(self.slide(self.triangle))
            o_dt = pd.Series(self.odims)
            if origin_grain == 'Q':
                o = np.array(pd.to_datetime(o_dt.dt.year.astype(str) + 'Q' +
                                            o_dt.dt.quarter.astype(str)))
            elif origin_grain == 'Y':
                o = np.array(o_dt.dt.year)
            else:
                o = self.odims
            o_new = np.unique(o)
            o = np.repeat(np.expand_dims(o, axis=1), len(o_new), axis=1)
            o_new = np.repeat(np.expand_dims(o_new, axis=0), len(o), axis=0)
            o_bool = np.repeat(np.expand_dims((o == o_new), axis=1),
                               len(self.ddims), axis=1)
            o_bool = self.expand_dims(o_bool)
            new_tri = np.repeat(np.expand_dims(orig, axis=-1),
                                o_bool.shape[-1], axis=-1)
            new_tri = np.swapaxes(np.sum(new_tri*o_bool, axis=2), -1, -2)
            # Then do Development
            dev_grain_dict = {'M': {'Y': 12, 'Q': 3, 'M': 1},
                              'Q': {'Y': 4, 'Q': 1}}
            keeps = dev_grain_dict[self.development_grain][development_grain]
            keeps = self.ddims % keeps == 0
            new_tri = new_tri[:, :, :, keeps]
            self.ddims = self.ddims[keeps]
            self.odims = o_new
            self.origin_grain = origin_grain
            self.development_grain = development_grain
            self.triangle = new_tri
            self.triangle = self.slide(self.triangle, direction='l')
            return self
        else:
            new_obj = copy.deepcopy(self)
            new_obj.grain(grain=grain, incremental=incremental, inplace=True)
            return new_obj

    # ---------------------------------------------------------------- #
    # ------------------------ Display Options ----------------------- #
    # ---------------------------------------------------------------- #
    def __repr__(self):
        if (self.triangle.shape[0], self.triangle.shape[1]) == (1, 1):
            data = self._repr_format()
            return data.to_string()
        else:
            data = 'Valuation: ' + self.valuation_date.strftime('%Y-%m') + \
                   '\nGrain:     ' + 'O' + self.origin_grain + \
                                     'D' + self.development_grain + \
                   '\nShape:     ' + str(self.shape) + \
                   '\nKeys:      ' + str(self.groupby) + \
                   '\nValues:    ' + str(list(self.vdims))
            return data

    def _repr_html_(self):
        ''' Jupyter/Ipython HTML representation '''
        if (self.triangle.shape[0], self.triangle.shape[1]) == (1, 1):
            data = self._repr_format()
            data = data.to_html(max_rows=pd.options.display.max_rows,
                                max_cols=pd.options.display.max_columns)
            return data
        else:
            data = pd.Series([self.valuation_date.strftime('%Y-%m'),
                             'O' + self.origin_grain + 'D'
                              + self.development_grain,
                              self.shape, self.groupby, list(self.vdims)],
                             index=['Valuation:', 'Grain:', 'Shape',
                                    'Keys:', "Values:"],
                             name='Triangle Summary').to_frame()
            return data.to_html(max_rows=pd.options.display.max_rows,
                                max_cols=pd.options.display.max_columns)

    def _repr_format(self):
        ''' Flatten to 2D DataFrame '''
        x = np.nansum(self.triangle, axis=0)
        x = np.nansum(x, axis=0)*self.nan_triangle()
        origin = pd.Series(self.odims).dt.to_period(self.origin_grain)
        return pd.DataFrame(x, index=origin, columns=self.ddims)

    def to_clipboard(self):
        if (self.triangle.shape[0], self.triangle.shape[1]) == (1, 1):
            self._repr_format().to_clipboard()

    # ---------------------------------------------------------------- #
    # ---------------------- Arithmetic Overload --------------------- #
    # ---------------------------------------------------------------- #
    def __add__(self, other):
        obj = copy.deepcopy(self)
        obj.triangle = self.triangle + other.triangle
        obj.vdims = np.array([None])
        return obj

    def __radd__(self, other):
        return self if other == 0 else self.__add__(other)

    def __sub__(self, other):
        obj = copy.deepcopy(self)
        obj.triangle = self.triangle - other.triangle
        obj.vdims = np.array([None])
        return obj

    def __mul__(self, other):
        obj = copy.deepcopy(self)
        obj.triangle = self.triangle * other.triangle
        obj.vdims = np.array([None])
        return obj

    def __truediv__(self, other):
        obj = copy.deepcopy(self)
        obj.triangle = self.triangle / other.triangle
        obj.vdims = np.array([None])
        return obj

    def sum(self):
        obj = copy.deepcopy(self)
        x = np.nansum(obj.triangle, axis=0)*obj.nan_triangle()
        obj.kdims = np.array([0])
        obj.triangle = np.expand_dims(x, axis=0)
        obj.groupby = [0]
        return obj

    # ---------------------------------------------------------------- #
    # ----------------------Slicing and indexing---------------------- #
    # ---------------------------------------------------------------- #
    class LocBase:
        ''' Base class for pandas style indexing '''
        def __init__(self, obj):
            self.obj = obj

        def get_idx(self, idx):
            if type(idx) is pd.Series:
                if len(idx) == len(self.obj.kdims):
                    idx = idx.to_frame()
                else:
                    idx = idx.to_frame().T
            elif type(idx) is tuple:
                idx = self.obj.idx_table().iloc[idx[0]:idx[0] + 1,
                                                idx[1]:idx[1] + 1]
            obj = copy.deepcopy(self.obj)
            obj.kdims = np.array(idx.index.unique())
            obj.vdims = np.array(idx.columns.unique())
            obj.iloc = Triangle.Ilocation(obj)
            obj.loc = Triangle.Location(obj)
            idx_slice = np.array(idx).flatten()
            x = tuple([np.unique(np.array(item))
                       for item in list(zip(*idx_slice))])
            obj.triangle = obj.triangle[x[0]][:, x[1]]
            obj.triangle[obj.triangle == 0] = np.nan
            return obj

    class Location(LocBase):
        ''' Class for pandas style .loc indexing '''
        def __getitem__(self, key):
            idx = self.obj.idx_table().loc[key]
            return self.get_idx(idx)

    class Ilocation(LocBase):
        ''' Class for pandas style .iloc indexing '''
        def __getitem__(self, key):
            idx = self.obj.idx_table().iloc[key]
            return self.get_idx(idx)

    def idx_table(self):
        temp = pd.DataFrame(list(self.kdims), columns=self.groupby)
        for num, item in enumerate(self.vdims):
            temp[item] = list(zip(np.arange(len(temp)),
                              (np.ones(len(temp))*num).astype(int)))
        temp.set_index(self.groupby, inplace=True)
        return temp

    def __getitem__(self, key):
        ''' Function for pandas style column indexing getting '''
        idx = self.idx_table()[key]
        return Triangle.LocBase(self).get_idx(idx)

    def __setitem__(self, key, value):
        ''' Function for pandas style column indexing setting '''
        idx = self.idx_table()
        idx[key] = 1
        self.vdims = np.array(idx.columns.unique())
        self.triangle = np.append(self.triangle, value.triangle, axis=1)

    def append(self, obj, index):
        return_obj = copy.deepcopy(self)
        x = pd.DataFrame(list(return_obj.kdims), columns=return_obj.groupby)
        new_idx = pd.DataFrame([index], columns=return_obj.groupby)
        x = x.append(new_idx)
        x.set_index(return_obj.groupby, inplace=True)
        return_obj.triangle = np.append(return_obj.triangle, obj.triangle,
                                        axis=0)
        return_obj.kdims = np.array(x.index.unique())
        return return_obj

    # ---------------------------------------------------------------- #
    # ------------------- Data Ingestion Functions ------------------- #
    # ---------------------------------------------------------------- #

    def get_date_axes(self, origin_date, development_date):
        ''' Function to find any missing origin dates or development dates that
            would otherwise mess up the origin/development dimensions.
        '''
        def complete_date_range(origin_date, development_date,
                                origin_grain, development_grain):
            ''' Determines origin/development combinations in full.  Useful for
                when the triangle has holes in it. '''
            origin_unique = \
                pd.PeriodIndex(start=origin_date.min(),
                               end=origin_date.max(),
                               freq=origin_grain).to_timestamp()
            development_unique = \
                pd.PeriodIndex(start=origin_date.min(),
                               end=development_date.max(),
                               freq=development_grain).to_timestamp()
            # Let's get rid of any development periods before origin periods
            cart_prod = cartesian_product(origin_unique, development_unique)
            cart_prod = cart_prod[cart_prod[:, 0] <= cart_prod[:, 1], :]
            return pd.DataFrame(cart_prod, columns=['origin', 'development'])

        cart_prod_o = \
            complete_date_range(pd.Series(origin_date.min()), development_date,
                                self.origin_grain, self.development_grain)
        cart_prod_d = \
            complete_date_range(origin_date, pd.Series(origin_date.max()),
                                self.origin_grain, self.development_grain)
        cart_prod_t = pd.DataFrame({'origin': origin_date,
                                   'development': development_date})
        cart_prod = cart_prod_o.append(cart_prod_d) \
                               .append(cart_prod_t).drop_duplicates()
        cart_prod = cart_prod[cart_prod['development'] >= cart_prod['origin']]
        return cart_prod

    def get_axes(self, data_agg, groupby, values,
                 origin_date, development_date):
        ''' Preps axes for the 4D triangle
        '''
        date_axes = self.get_date_axes(origin_date, development_date)
        #if len(groupby) != 0:
        kdims = data_agg[groupby].drop_duplicates()
        kdims['key'] = 1
        #else:
        #    kdims = pd.DataFrame({'Total': [0], 'key': 1})
        date_axes['key'] = 1
        all_axes = pd.merge(date_axes, kdims, on='key').drop('key', axis=1)
        data_agg = \
            all_axes.merge(data_agg, how='left',
                           left_on=['origin', 'development'] + groupby,
                           right_on=[origin_date, development_date] + groupby) \
                    .fillna(0)[['origin', 'development'] + groupby + values]
        data_agg['development'] = development_lag(data_agg['origin'],
                                                  data_agg['development'])
        return data_agg

    # ---------------------------------------------------------------- #
    # ------------------- Class Utility Functions -------------------- #
    # ---------------------------------------------------------------- #
    def nan_triangle(self):
        '''Given the current triangle shape and grain, it determines the
           appropriate placement of NANs in the triangle for future valuations.
           This becomes useful when managing array arithmetic.
        '''
        grain_dict = {'Y': {'Y': 1, 'Q': 4, 'M': 12},
                      'Q': {'Q': 1, 'M': 3},
                      'M': {'M': 1}}
        val_lag = self.triangle.shape[3] % \
            grain_dict[self.origin_grain][self.development_grain]
        val_lag = 1 if val_lag == 0 else val_lag
        goods = (np.arange(self.triangle.shape[2]) *
                 grain_dict[self.origin_grain][self.development_grain] +
                 val_lag)[::-1]
        blank_bool = np.ones(self.triangle[0, 0].shape).cumsum(axis=1) <= \
            np.repeat(np.expand_dims(goods, axis=1),
                      self.triangle[0, 0].shape[1], axis=1)
        blank = (blank_bool*1.)
        blank[~blank_bool] = np.nan
        return blank

    def slide(self, triangle, direction='r'):
        ''' Facilitates swapping alignment of triangle between development
            period and development date. '''
        nan_tri = self.nan_triangle()
        r = (nan_tri.shape[1] - np.nansum(nan_tri, axis=1)).astype(int)
        r = -r if direction == 'l' else r
        k, v, rows, column_indices = \
            np.ogrid[:triangle.shape[0], :triangle.shape[1],
                     :triangle.shape[2], :triangle.shape[3]]
        r[r < 0] += nan_tri.shape[1]
        column_indices = column_indices - r[:, np.newaxis]
        return triangle[k, v, rows, column_indices]

    def expand_dims(self, tri_2d):
        '''Expands from one 2D triangle to full 4D object
        '''
        k = len(self.kdims)
        v = len(self.vdims)
        tri_3d = np.repeat(np.expand_dims(tri_2d, axis=0), v, axis=0)
        return np.repeat(np.expand_dims(tri_3d, axis=0), k, axis=0)
