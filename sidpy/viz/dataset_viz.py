# -*- coding: utf-8 -*-
"""
Utilities for generating static image and line plots of near-publishable quality

Created on Thu May 05 13:29:12 2020

@author: Gerd Duscher
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sidpy

import sidpy
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import ipywidgets
from IPython.display import display
import scipy


# import matplotlib.animation as animation

from ..hdf.dtype_utils import is_complex_dtype
if sys.version_info.major == 3:
    unicode = str

default_cmap = plt.cm.viridis


class CurveVisualizer(object):
    def __init__(self, dset, spectrum_number=0, figure=None, **kwargs):
        scale_bar = kwargs.pop('scale_bar', False)
        colorbar = kwargs.pop('colorbar', True)
        set_title = kwargs.pop('set_title', True)

        if not isinstance(dset, sidpy.Dataset):
            raise TypeError('dset should be a sidpy.Dataset object')
        if dset.data_type.name != 'SPECTRUM':
            raise TypeError("sidpy.Dataset should have DataType 'Spectrum' ")
        fig_args = dict()
        temp = kwargs.pop('figsize', None)
        if temp is not None:
            fig_args['figsize'] = temp

        if figure is None:
            self.fig = plt.figure(**fig_args)
        else:
            self.fig = figure

        self.dset = dset
        self.selection = []
        self.spectral_dims = []

        for dim, axis in dset._axes.items():
            if axis.dimension_type == sidpy.DimensionType.SPECTRAL:
                self.selection.append(slice(None))
                self.spectral_dims.append(dim)
            else:
                if spectrum_number <= dset.shape[dim]:
                    self.selection.append(slice(spectrum_number, spectrum_number + 1))
                    self.spectral_dims.append(dim)
                else:
                    self.spectrum_number = 0
                    self.selection.append(slice(0, 1))
                    self.spectral_dims.append(dim)

        # Handle the simple cases first:
        fig_args = dict()
        temp = kwargs.pop('figsize', None)
        if temp is not None:
            fig_args['figsize'] = temp

        self.dim = self.dset._axes[self.spectral_dims[0]]

        if is_complex_dtype(dset.dtype):
            # Plot real and imaginary
            self.fig, self.axes = plt.subplots(nrows=2, **fig_args)

            self.axes[0].plot(self.dim.values, self.dset.squeeze().abs().compute(), **kwargs)
            if set_title:
                self.axes[0].set_title(self.dset.title + '\n(Magnitude)', pad=15)
            self.axes[0].set_xlabel(self.dset.labels[0])
            self.axes[0].set_ylabel(self.dset.data_descriptor)
            self.axes[0].ticklabel_format(style='sci', scilimits=(-2, 3))

            if set_title:
                self.axes[1].set_title(self.dset.title + '\n(Phase)', pad=15)
            self.axes[1].set_ylabel('Phase (rad)')
            self.axes[1].set_xlabel(self.dset.labels[0])  # + x_suffix)
            self.axes[1].ticklabel_format(style='sci', scilimits=(-2, 3))

            self.fig.tight_layout()
            self.fig.canvas.draw_idle()

        else:
            self.axis = self.fig.add_subplot(1, 1, 1, **fig_args)
            self.axis.plot(self.dim.values, self.dset.compute(), **kwargs)
            if self.dset.variance is not None:
                self.axis.fill_between(self.dim.values,
                                      self.dset.compute()-self.dset.variance,
                                      self.dset.compute()+self.dset.variance,
                                      alpha = 0.3, **kwargs)
            if set_title:
                self.axis.set_title(self.dset.title, pad=15)
            self.axis.set_xlabel(self.dset.labels[self.spectral_dims[0]])
            self.axis.set_ylabel(self.dset.data_descriptor)
            self.axis.ticklabel_format(style='sci', scilimits=(-2, 3))
            self.fig.canvas.draw_idle()


class ImageVisualizer(object):
    """
    Interactive display of image plot

    The stack can be scrolled through with a mouse wheel or the slider
    The usual zoom effects of matplotlib apply.
    Works on every backend because it only depends on matplotlib.

    Important: keep a reference to this class to maintain interactive properties so usage is:

    >>view = plot_stack(dataset, {'spatial':[0,1], 'stack':[2]})

    Input:
    ------
    - dset: NSIDask _dataset
    - figure: optional
            matplotlib figure
    - image_number optional
            if this is a stack of images we can choose which one we want.
    kwargs optional
            additional arguments for matplotlib and a boolean value with keyword 'scale_bar'

    """

    def __init__(self, dset, figure=None, image_number=0, **kwargs):
        """
        plotting of data according to two axis marked as SPATIAL in the dimensions
        """
        if not isinstance(dset, sidpy.Dataset):
            raise TypeError('dset should be a sidpy.Dataset object')
        fig_args = dict()
        temp = kwargs.pop('figsize', None)
        if temp is not None:
            fig_args['figsize'] = temp
        
        if figure is None:
            self.fig = plt.figure(**fig_args)
        else:
            self.fig = figure

        self.dset = dset
        self.image_number = image_number

        self.selection = []
        self.image_dims = []

        for dim, axis in dset._axes.items():
            if axis.dimension_type in [sidpy.DimensionType.SPATIAL, sidpy.DimensionType.RECIPROCAL]:
                self.selection.append(slice(None))
                self.image_dims.append(dim)
            else:
                if image_number <= dset.shape[dim]:
                    self.selection.append(slice(image_number, image_number + 1))
                else:
                    self.image_number = 0
                    self.selection.append(slice(0, 1))
        if len(self.image_dims) != 2:
            raise TypeError('We need two dimensions with dimension_type SPATIAL or RECIPROCAL to plot an image')

        if is_complex_dtype(self.dset.dtype):
            self.plot_complex_image(**kwargs)
        else:
            self.axis = self.fig.add_subplot(1, 1, 1)
            self.plot_image(**kwargs)

        if self.dset.variance is not None:
            if self.dset.variance.shape != self.dset.shape:
                raise ValueError('Variance array must have the same dimensionality as the dataset')

            self._variance_button = ipywidgets.widgets.Dropdown(options=[('z', 1), ('σ', 2), ('z + σ', 3), ('z - σ', 4)],
                                                                value=1,
                                                                description='Image',
                                                                tooltip='What to plot: image data (z), variance of z (σ), etc.',
                                                                layout=ipywidgets.Layout(width='20%', height='40px', ))

            self._variance_button.observe(self._var_button_event, 'value')  # pixel or unit wise
            self.fig.canvas.draw_idle()
            drop_down_menu = ipywidgets.HBox([self._variance_button])
            display(drop_down_menu)

    def plot_image(self, **kwargs):
        from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar

        scale_bar = kwargs.pop('scale_bar', False)
        self.colorbar = kwargs.pop('colorbar', True)
        set_title = kwargs.pop('set_title', True)
        rgb = False
        if set_title:
            self.axis.set_title(self.dset.title)
            if len(self.dset.shape) > 2:
                if self.dset.shape[2] > 4:
                    self.axis.set_title(self.dset.title + '_image {}'.format(self.image_number))
                else:
                    rgb = True

        if rgb:
            self.img = self.axis.imshow(self.dset, extent=self.dset.get_extent(self.image_dims), **kwargs)
        else:
            self.img = self.axis.imshow(self.dset[tuple(self.selection)].squeeze().T,
                                        extent=self.dset.get_extent(self.image_dims), **kwargs)
        self.axis.set_xlabel(self.dset.labels[self.image_dims[0]])
        self.axis.set_ylabel(self.dset.labels[self.image_dims[1]])
        if scale_bar:

            plt.axis('off')
            extent = self.dset.get_extent(self.image_dims)
            size_of_bar = int((extent[1] - extent[0]) / 10 + .5)
            if size_of_bar < 1:
                size_of_bar = 1
            scalebar = AnchoredSizeBar(plt.gca().transData,
                                       size_of_bar, '{} {}'.format(size_of_bar,
                                                                   self.dset._axes[self.image_dims[0]].units),
                                       'lower left',
                                       pad=1,
                                       color='white',
                                       frameon=False,
                                       size_vertical=.2)

            plt.gca().add_artist(scalebar)

        if self.colorbar:
            cbar = self.fig.colorbar(self.img)
            cbar.set_label(self.dset.data_descriptor)

            self.axis.ticklabel_format(style='sci', scilimits=(-2, 3))
            self.fig.tight_layout()
        self.img.axes.figure.canvas.draw_idle()

    def plot_complex_image(self, **kwargs):
        from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
        scale_bar = kwargs.pop('scale_bar', False)
        self.colorbar = kwargs.pop('colorbar', True)

        self.axes = []
        # magnitude
        self.axes.append(self.fig.add_subplot(121))
        self.img = self.axes[0].imshow(self.dset[tuple(self.selection)].abs().squeeze().T,
                                       extent=self.dset.get_extent(self.image_dims), **kwargs)
        self.axes[0].set_xlabel(self.dset.labels[self.image_dims[0]])
        self.axes[0].set_ylabel(self.dset.labels[self.image_dims[1]])
        self.axes[0].set_title(self.dset.title + '\n(Magnitude)', pad=15)
        if self.colorbar:
            cbar = self.fig.colorbar(self.img)
            cbar.set_label("{} [{}]".format(self.dset.quantity, self.dset.units))
        self.axes[0].ticklabel_format(style='sci', scilimits=(-2, 3))

        # phase
        self.axes.append(self.fig.add_subplot(122, sharex=self.axes[0], sharey=self.axes[0]))
        self.img_c = self.axes[1].imshow(self.dset[tuple(self.selection)].squeeze().angle().T,
                                         extent=self.dset.get_extent(self.image_dims), **kwargs)
        self.axes[1].set_xlabel(self.dset.labels[self.image_dims[0]])
        self.axes[1].set_ylabel(self.dset.labels[self.image_dims[1]])
        self.axes[1].set_title(self.dset.title + '\n(Phase)', pad=15)
        if self.colorbar:
            cbar_c = self.fig.colorbar(self.img_c)
            cbar_c.set_label(self.dset.data_descriptor)
        self.axes[1].ticklabel_format(style='sci', scilimits=(-2, 3))

        if scale_bar:
            for ax in self.axes:
                ax.axis('off')
                extent = self.dset.get_extent(self.image_dims)
                size_of_bar = int((extent[1] - extent[0]) / 10 + .5)
                if size_of_bar < 1:
                    size_of_bar = 1
                scalebar = AnchoredSizeBar(ax.transData,
                                           size_of_bar, '{} {}'.format(size_of_bar,
                                                                       self.dset._axes[self.image_dims[0]].units),
                                           'lower left',
                                           pad=1,
                                           color='white',
                                           frameon=False,
                                           size_vertical=.2)
                ax.add_artist(scalebar)

        self.fig.tight_layout()

    def _var_button_event(self, event):
        disp = event.new
        self._update_image(disp)

    def _update_image(self, event_value, **kwargs):
        _data = {1: self.dset[tuple(self.selection)].squeeze().T,
                 2: self.dset.variance[tuple(self.selection)].squeeze().T,
                 3: self.dset.variance[tuple(self.selection)].squeeze().T + self.dset[tuple(self.selection)].squeeze().T,
                 4: self.dset[tuple(self.selection)].squeeze().T - self.dset.variance[tuple(self.selection)].squeeze().T}

        if is_complex_dtype(self.dset.dtype):
            _dat = np.array(_data[event_value] + 0*1j)
            self.img.set_data(np.abs(_dat))
            self.img.set_clim(np.abs(_dat).min(), np.abs(_dat).max())

            self.img_c.set_data(np.angle(_dat))
            self.img_c.set_clim(np.angle(_dat).min(), np.angle(_dat).max())
        else:
            self.img.set_data(_data[event_value])
            self.img.set_clim(_data[event_value].min(), _data[event_value].max())


class ImageStackVisualizer(object):
    """
    Interactive display of image stack plot

    The stack can be scrolled through with a mouse wheel or the slider
    The usual zoom effects of matplotlib apply.
    Works on every backend because it only depends on matplotlib.

    Important: keep a reference to this class to maintain interactive properties so usage is:

    >>kwargs = {'scale_bar': True, 'cmap': 'hot'}

    >>view = ImageStackVisualizer(dataset, **kwargs )

    Input:
    ------
    - dset: sidpy Dataset
    - figure: optional
            matplotlib figure
    - kwargs: optional
            matplotlib additional arguments like {cmap: 'hot'}
    """

    def __init__(self, dset, figure=None, **kwargs):

        if not isinstance(dset, sidpy.Dataset):
            raise TypeError('dset should be a sidpy.Dataset object')
        fig_args = dict()
        temp = kwargs.pop('figsize', None)
        if temp is not None:
            fig_args['figsize'] = temp
        self.set_title = kwargs.pop('set_title', True)
        
        if figure is None:
            self.fig = plt.figure(**fig_args)
        else:
            self.fig = figure

        if dset.ndim < 3:
            raise TypeError('dataset must have at least three dimensions')

        self.stack_dim = -1
        self.image_dims = []
        self.selection = []
        for dim, axis in dset._axes.items():
            if axis.dimension_type in [sidpy.DimensionType.SPATIAL, sidpy.DimensionType.RECIPROCAL]:
                self.selection.append(slice(None))
                self.image_dims.append(dim)
            elif axis.dimension_type == sidpy.DimensionType.TEMPORAL or len(dset) == 3:
                self.selection.append(slice(0, 1))
                self.stack_dim = dim
            else:
                self.selection.append(slice(0, 1))

        if len(self.image_dims) != 2:
            raise TypeError('We need two dimensions with dimension_type spatial to plot an image')

        if self.stack_dim < 0:
            raise TypeError('We need one dimensions with dimension_type stack, time or frame')

        if len(self.image_dims) < 2:
            raise TypeError('Two SPATIAL dimension are necessary for this plot')

        self.dset = dset

        # self.axis = self.fig.add_axes([0.0, 0.2, .9, .7])
        self.ind = 0
        self.plot_fit_labels = False

        self.number_of_slices = self.dset.shape[self.stack_dim]
        
        if self.set_title:
            if 'fit_dataset' in dir(dset):
                if dset.fit_dataset:
                    if dset.metadata['fit_parms_dict']['fit_parameters_labels'] is not None: 
                        self.plot_fit_labels = True
                        img_titles = dset.metadata['fit_parms_dict']['fit_parameters_labels']
                        self.image_titles = ['Fitting Parm: ' + img_titles[k] for k in range(len(img_titles))]
                    else:
                        self.image_titles = 'Fitting Maps: ' + dset.title + '\n use scroll wheel to navigate images'    
                else:
                    self.image_titles = 'Fitting Maps: ' + dset.title + '\n use scroll wheel to navigate images'
            else:
                self.image_titles = 'Image stack: ' + dset.title + '\n use scroll wheel to navigate images'
        
        self.axis = None
        self.plot_image(**kwargs)
        self.axis = plt.gca()
        # self.axis.set_title(image_titles)
        self.img.axes.figure.canvas.mpl_connect('scroll_event', self._onscroll)

        self.play = ipywidgets.Play(value=0,
                                    min=0,
                                    max=self.number_of_slices,
                                    step=1,
                                    interval=500,
                                    description="Press play",
                                    disabled=False)
        self.slider = ipywidgets.IntSlider(value=0,
                                           min=0,
                                           max=self.number_of_slices,
                                           continuous_update=False,
                                           description="Frame:")
        # set the slider function
        ipywidgets.interactive(self._update, frame=self.slider)
        # link slider and play function
        ipywidgets.jslink((self.play, 'value'), (self.slider, 'value'))

        # We add a button to average the images
        self.button = ipywidgets.widgets.ToggleButton(value=False,
                                                      description='Average',
                                                      disabled=False,
                                                      button_style='',
                                                      tooltip='Average Images of Stack')

        self.average = False
        self.button.observe(self._average_slices, 'value')

        if self.dset.variance is not None:
            if self.dset.variance.shape != self.dset.shape:
                raise ValueError('Variance array must have the same dimensionality as the dataset')

            self._variance_button = ipywidgets.widgets.Dropdown(options=[('z', 1), ('σ', 2), ('z + σ', 3), ('z - σ', 4)],
                                                                value=1,
                                                                tooltip='What to plot: image data (z), variance of z (σ), etc.',)

            self._variance_button.observe(self._var_button_event, 'value')

            widg0 = ipywidgets.HBox([self.play, self.slider])
            widg1 = ipywidgets.HBox([self.button, self._variance_button])
            widg = ipywidgets.VBox([widg0, widg1])
            self.display = 1  # 0 - without var, 1 z, 2 sigma, 3 z-sigma, 4 z+sigma
        else:
            widg = ipywidgets.HBox([self.play, self.slider, self.button])
            self.display = 0

        display(widg)

        # self.anim = animation.FuncAnimation(self.fig, self._updatefig, interval=200, blit=False, repeat=True)
        self._update()

    def plot_image(self, **kwargs):

        from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar

        scale_bar = kwargs.pop('scale_bar', False)
        colorbar = kwargs.pop('colorbar', True)

        self.axis = plt.gca()
        if self.set_title:
            self.axis.set_title(self.dset.title)

        self.img = self.axis.imshow(self.dset[tuple(self.selection)].squeeze().T,
                                    extent=self.dset.get_extent(self.image_dims), **kwargs)
        self.axis.set_xlabel(self.dset.labels[self.image_dims[0]])
        self.axis.set_ylabel(self.dset.labels[self.image_dims[1]])

        if scale_bar:

            plt.axis('off')
            extent = self.dset.get_extent(self.image_dims)
            size_of_bar = int((extent[1] - extent[0]) / 10 + .5)
            if size_of_bar < 1:
                size_of_bar = 1
            scalebar = AnchoredSizeBar(plt.gca().transData,
                                       size_of_bar, '{} {}'.format(size_of_bar,
                                                                   self.dset._axes[self.image_dims[0]].units),
                                       'lower left',
                                       pad=1,
                                       color='white',
                                       frameon=False,
                                       size_vertical=.2)

            plt.gca().add_artist(scalebar)

        if colorbar:
            cbar = self.fig.colorbar(self.img)
            cbar.set_label(self.dset.data_descriptor)

            self.axis.ticklabel_format(style='sci', scilimits=(-2, 3))
            self.fig.tight_layout()

        self.img.axes.figure.canvas.draw_idle()

    def _average_slices(self, event):
        self.average = event.new
        self._update(self.ind)
        # if event.new:
        #     if len(self.dset.shape) == 3:
        #         image_stack = self.dset
        #     else:
        #         stack_selection = self.selection.copy()
        #         stack_selection[self.stack_dim] = slice(None)
        #         image_stack = self.dset[stack_selection].squeeze()
        #
        #     self.img.set_data(image_stack.mean(axis=self.stack_dim).T)
        #     self.fig.canvas.draw_idle()
        # elif event.old:
        #     self.ind = self.ind % self.number_of_slices
        #    self._update(self.ind)

    def _onscroll(self, event):
        if event.button == 'up':
            self.slider.value = (self.slider.value + 1) % self.number_of_slices
        else:
            self.slider.value = (self.slider.value - 1) % self.number_of_slices
        self.ind = int(self.slider.value)

    def _var_button_event(self, event):
        self.display = event.new
        self._update(self.ind)

    def _update(self, frame=0):
        if self.display == 2:
            _dset = self.dset.variance
        elif self.display == 3:
            _dset = self.dset + self.dset.variance
        elif self.display == 4:
            _dset = self.dset - self.dset.variance
        else:
            _dset = self.dset

        if self.average:
            if len(self.dset.shape) == 3:
                image_stack = _dset
            else:
                stack_selection = self.selection.copy()
                stack_selection[self.stack_dim] = slice(None)
                image_stack = self.dset[stack_selection].squeeze()

            self.img.set_data(image_stack.mean(axis=self.stack_dim).T)
            self.fig.canvas.draw_idle()
        else:
            self.ind = frame
            self.selection[self.stack_dim] = slice(frame, frame + 1)
            self.img.set_data((_dset[tuple(self.selection)].squeeze()).T)
            self.img.set_clim(_dset[tuple(self.selection)].min(), _dset[tuple(self.selection)].max())
            self.img.axes.figure.canvas.draw_idle()

            if self.plot_fit_labels:
                self.axis.set_title(self.image_titles[frame])
            else:
                self.axis.set_title(self.image_titles)


class SpectralImageVisualizerBase(object):
    """
    ### Interactive spectrum imaging plot

    If there is a 4D dataset, and one of them is named 'channel', 
    then you can plot the channel spectra too

    """

    def __init__(self, dset, figure=None, horizontal=True, **kwargs):

        if not isinstance(dset, sidpy.Dataset):
            raise TypeError('dset should be a sidpy.Dataset object')
        
        scale_bar = kwargs.pop('scale_bar', False)
        colorbar = kwargs.pop('colorbar', True)
        self.set_title = kwargs.pop('set_title', True)
        
        fig_args = dict()
        temp = kwargs.pop('figsize', None)
        if temp is not None:
            fig_args['figsize'] = temp

        if figure is None:
            self.fig = plt.figure(**fig_args)
        else:
            self.fig = figure

        self.image_dims = []
        self.energy_axis = []
        self.channel_axis = []
        self.dset = dset
        self.verify_dataset()

        self.horizontal = horizontal
        self.x = 0
        self.y = 0
        self.bin_x = 1
        self.bin_y = 1

        self.set_dataset()

        if horizontal:
            self.axes = self.fig.subplots(ncols=2)
        else:
            self.axes = self.fig.subplots(nrows=2, **fig_args)

        if self.set_title:
            self.fig.canvas.manager.set_window_title(self.dset.title)

        self.set_image(**kwargs)

        self.set_spectrum()

        self.fig.tight_layout()
        self.cid = self.axes[1].figure.canvas.mpl_connect('button_press_event', self._onclick)
        self.fig.canvas.draw_idle()

    def verify_dataset(self):
        dset = self.dset

        if len(dset.shape) < 3:
            raise TypeError('dataset must have at least three dimensions')
        if len(dset.shape) > 4:
            raise TypeError('dataset must have at most four dimensions')

        # We need one stack dim and two image dimes as lists in dictionary

        selection = []
        image_dims = []
        spectral_dim = []
        channel_dim = []
        for dim, axis in dset._axes.items():
            if axis.dimension_type in [sidpy.DimensionType.SPATIAL, sidpy.DimensionType.RECIPROCAL]:
                selection.append(slice(None))
                image_dims.append(dim)
            elif axis.dimension_type == sidpy.DimensionType.SPECTRAL:
                selection.append(slice(0, 1))
                spectral_dim.append(dim)
            elif axis.dimension_type == sidpy.DimensionType.CHANNEL:
                channel_dim.append(dim)
            else:
                selection.append(slice(0, 1))
        
        if len(image_dims) != 2:
            raise TypeError('We need two dimensions with dimension_type SPATIAL: to plot an image')
        if len(channel_dim) >1:
            raise ValueError("We have more than one Channel Dimension, this won't work for the visualizer")
        if len(spectral_dim)>1:
            raise ValueError("We have more than one Spectral Dimension, this won't work for the visualizer...")

        if self.dset.variance is not None:
            if self.dset.variance.shape != self.dset.shape:
                raise ValueError('Variance array must have the same dimensionality as the dataset')

        if len(dset.shape) == 4:
            if len(channel_dim) != 1:
                raise TypeError("We need one dimension with type CHANNEL \
                    for a spectral image plot for a 4D dataset")
        elif len(dset.shape)==3:
            if len(spectral_dim) != 1:
                raise TypeError("We need one dimension with dimension_type SPECTRAL \
                 to plot a spectra for a 3D dataset")

        self.image_dims = image_dims
        self.energy_axis = spectral_dim[0]
        if len(channel_dim)>0:
            self.channel_axis = channel_dim
        return True

    def set_dataset(self):

        size_x = self.dset.shape[self.image_dims[0]]
        size_y = self.dset.shape[self.image_dims[1]]

        self.energy_scale = self.dset._axes[self.energy_axis].values
        self.extent = [0, size_x, size_y, 0]
        self.rectangle = [0, size_x, 0, size_y]
        self.scaleX = 1.0
        self.scaleY = 1.0
        self.analysis = []
        self.plot_legend = False

        self.extent_rd = self.dset.get_extent(self.image_dims)

    def set_image(self, **kwargs):
        if len(self.channel_axis)>0:
            self.image = self.dset.mean(axis=(self.energy_axis,self.channel_axis[0]))
        else:
            self.image = self.dset.mean(axis=(self.energy_axis))

        self.axes[0].imshow(self.image.T, extent=self.extent, **kwargs)
        
        if 1 in self.dset.shape:
            self.axes[0].set_aspect('auto')
            self.axes[0].get_yaxis().set_visible(False)
        else:
            self.axes[0].set_aspect('equal')

        self.axes[0].set_xticks(np.linspace(self.extent[0], self.extent[1], 5))
        self.axes[0].set_xticklabels(np.round(np.linspace(self.extent[0], self.extent[1], 5),2))

        self.axes[0].set_yticks(np.linspace(self.extent[2], self.extent[3], 5))
        self.axes[0].set_yticklabels(np.round(np.linspace(self.extent[2], self.extent[3], 5),1))

        self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                 'px'))
        self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                        'px'))
        self.rect = patches.Rectangle((0, 0), self.bin_x, self.bin_y, linewidth=1, edgecolor='r',
                                      facecolor='red', alpha=0.2)

        self.axes[0].add_patch(self.rect)

    def set_spectrum(self):
        self.intensity_scale = 1.
        self.spectrum = self.get_spectrum()
        if len(self.energy_scale)!=self.spectrum.shape[0]:
            self.spectrum = self.spectrum.T
        self.axes[1].plot(self.energy_scale, self.spectrum.compute())
        # add variance shadow graph
        if self.variance is not None:
            #3d - many curves
            if len(self.variance.shape) > 1:
                for i in range(len(self.variance)):
                    self.axes[1].fill_between(self.energy_scale,
                                              self.spectrum.compute().T[i] - self.variance[i],
                                              self.spectrum.compute().T[i] + self.variance[i],
                                              alpha=0.3) # , **kwargs)
            # 2d - one curve at each point
            else:
                self.axes[1].fill_between(self.energy_scale,
                                          self.spectrum.compute() - self.variance,
                                          self.spectrum.compute() + self.variance,
                                          alpha=0.3) # , **self.kwargs)

        self.axes[1].set_title('spectrum {}, {}'.format(self.x, self.y))

        self.xlabel = self.dset.labels[self.energy_axis]
        self.ylabel = self.dset.data_descriptor
        self.axes[1].set_xlabel(self.dset.labels[self.energy_axis])  # + x_suffix)
        self.axes[1].set_ylabel(self.dset.data_descriptor)
        self.axes[1].ticklabel_format(style='sci', scilimits=(-2, 3))
        self.fig.tight_layout()
        self.cid = self.axes[1].figure.canvas.mpl_connect('button_press_event', self._onclick)

        self.button = ipywidgets.widgets.Dropdown( options=[('Pixel Wise', 1), ('Units Wise', 2)],
                            value=1,
                            description='Image',
                            tooltip='How to plot spatial data: Pixel Wise (by px), Units wise (in given units)', 
                            layout = ipywidgets.Layout(width='30%', height='50px',))

        self.button.observe(self._pw_uw, 'value') #pixel or unit wise
        self.fig.canvas.draw_idle()
        widg = ipywidgets.HBox([self.button])
        display(widg)
    
    def _update_image(self, event_value):
        #pixel wise or unit wise listener
        if event_value==1:
            self.axes[0].set_xticks(np.linspace(self.extent[0], self.extent[1], 5))
            self.axes[0].set_xticklabels(np.round(np.linspace(self.extent[0], self.extent[1], 5),2))

            self.axes[0].set_yticks(np.linspace(self.extent[2], self.extent[3], 5))
            self.axes[0].set_yticklabels(np.round(np.linspace(self.extent[2], self.extent[3], 5),2))

            self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                     'px'))
            self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                         'px'))
        else:
            self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                     self.dset._axes[self.image_dims[0]].units))
            self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                            self.dset._axes[self.image_dims[1]].units))

            self.axes[0].set_xticks(np.linspace(self.extent[0], self.extent[1], 5),)
            self.axes[0].set_xticklabels(np.round(np.linspace(self.extent_rd[0], self.extent_rd[1], 5), 2))

            self.axes[0].set_yticks(np.linspace(self.extent[2], self.extent[3], 5),)
            self.axes[0].set_yticklabels(np.round(np.linspace(self.extent_rd[2], self.extent_rd[3], 5), 2))


            self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                        self.dset._axes[self.image_dims[0]].units))

            self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                            self.dset._axes[self.image_dims[1]].units))

            if self.dset._axes[self.image_dims[0]].units =='m':
                scaled_values_y = self.dset._axes[self.image_dims[1]].values*1E9
                scaled_values_x = self.dset._axes[self.image_dims[0]].values*1E9
                if scaled_values_x.mean() >=0.1 and  scaled_values_x.mean() <=1000:
                    self.axes[0].set_xticks(np.linspace(self.extent[0], self.extent[1], 5),)
                    self.axes[0].set_xticklabels(np.round(np.linspace(scaled_values_x[0], scaled_values_x[-1], 5), 2))

                    self.axes[0].set_yticks(np.linspace(self.extent[2], self.extent[3], 5),)
                    self.axes[0].set_yticklabels(np.round(np.linspace(scaled_values_y[0], scaled_values_y[-1], 5), 2))
                    
                    self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                        'nm'))
            
                    self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                            'nm'))
                    
        return

    def set_bin(self, bin_xy):
        old_bin_x = self.bin_x
        old_bin_y = self.bin_y
        if isinstance(bin_xy, list):
            self.bin_x = int(bin_xy[0])
            self.bin_y = int(bin_xy[1])
        else:
            self.bin_x = int(bin_xy)
            self.bin_y = int(bin_xy)

        if self.bin_x > self.dset.shape[self.image_dims[0]]:
            self.bin_x = self.dset.shape[self.image_dims[0]]
        if self.bin_y > self.dset.shape[self.image_dims[1]]:
            self.bin_y = self.dset.shape[self.image_dims[1]]

        self.rect.set_width(self.rect.get_width() * self.bin_x / old_bin_x)
        self.rect.set_height((self.rect.get_height() * self.bin_y / old_bin_y))
        if self.x + self.bin_x > self.dset.shape[self.image_dims[0]]:
            self.x = self.dset.shape[0] - self.bin_x
        if self.y + self.bin_y > self.dset.shape[self.image_dims[1]]:
            self.y = self.dset.shape[1] - self.bin_y

        self.rect.set_xy([self.x * self.rect.get_width() / self.bin_x + self.rectangle[0],
                          self.y * self.rect.get_height() / self.bin_y + self.rectangle[2]])
        self._update()

    def get_spectrum(self):

        if self.x > self.dset.shape[self.image_dims[0]] - self.bin_x:
            self.x = self.dset.shape[self.image_dims[0]] - self.bin_x
        if self.y > self.dset.shape[self.image_dims[1]] - self.bin_y:
            self.y = self.dset.shape[self.image_dims[1]] - self.bin_y
        selection = []

        for dim, axis in self.dset._axes.items():
            if axis.dimension_type == sidpy.DimensionType.SPATIAL:
                if dim == self.image_dims[0]:
                    selection.append(slice(self.x, self.x + self.bin_x))
                else:
                    selection.append(slice(self.y, self.y + self.bin_y))

            elif axis.dimension_type == sidpy.DimensionType.SPECTRAL:
                selection.append(slice(None))
            elif axis.dimension_type == sidpy.DimensionType.CHANNEL:
                selection.append(slice(None))
            else:
                selection.append(slice(0, 1))
        
        self.spectrum = self.dset[tuple(selection)].mean(axis=tuple(self.image_dims))

        if self.dset.variance is not None:
            self.variance = self.dset.variance[tuple(selection)].mean(axis=tuple(self.image_dims))
        else:
            self.variance = None

        # * self.intensity_scale[self.x,self.y]
        return self.spectrum.squeeze()

    def _onclick(self, event):
        self.event = event
        if event.inaxes in [self.axes[0]]:
            x = int(event.xdata)
            y = int(event.ydata)

            x = int(x - self.rectangle[0])
            y = int(y - self.rectangle[2])

            if x >= 0 and y >= 0:
                if x <= self.rectangle[1] and y <= self.rectangle[3]:
                    self.x = int(x / (self.rect.get_width() / self.bin_x))
                    self.y = int(y / (self.rect.get_height() / self.bin_y))

                    if self.x + self.bin_x > self.dset.shape[self.image_dims[0]]:
                        self.x = self.dset.shape[self.image_dims[0]] - self.bin_x
                    if self.y + self.bin_y > self.dset.shape[self.image_dims[1]]:
                        self.y = self.dset.shape[self.image_dims[1]] - self.bin_y

                    self.rect.set_xy([self.x * self.rect.get_width() / self.bin_x + self.rectangle[0],
                                      self.y * self.rect.get_height() / self.bin_y + self.rectangle[2]])
            self._update()
        else:
            if event.dblclick:
                bottom = float(self.spectrum.min())
                if bottom < 0:
                    bottom *= 1.02
                else:
                    bottom *= 0.98
                top = float(self.spectrum.max())
                if top > 0:
                    top *= 1.02
                else:
                    top *= 0.98

                self.axes[1].set_ylim(bottom=bottom, top=top)

    def _update(self, ev=None):

        xlim = self.axes[1].get_xlim()
        ylim = self.axes[1].get_ylim()
        self.axes[1].clear()
        self.get_spectrum()
        if len(self.energy_scale)!=self.spectrum.shape[0]:
            self.spectrum = self.spectrum.T
        self.axes[1].plot(self.energy_scale, self.spectrum.compute(), label='experiment')

        if self.dset.variance is not None:
            #3d - many curves
            if len(self.variance.shape) > 1:
                for i in range(len(self.variance)):
                    self.axes[1].fill_between(self.energy_scale,
                                              self.spectrum.compute().T[i] - self.variance[i],
                                              self.spectrum.compute().T[i] + self.variance[i],
                                              alpha=0.3)
            # 2d - one curve at each point
            else:
                self.axes[1].fill_between(self.energy_scale,
                                          self.spectrum.compute() - self.variance,
                                          self.spectrum.compute() + self.variance,
                                          alpha=0.3)

        self.axes[1].set_title('spectrum {}, {}'.format(self.x, self.y))

        self.axes[1].set_xlim(xlim)
        #self.axes[1].set_ylim(ylim)
        self.axes[1].set_xlabel(self.xlabel)
        self.axes[1].set_ylabel(self.ylabel)

        self.fig.canvas.draw_idle()

    def set_legend(self, set_legend):
        self.plot_legend = set_legend

    def get_xy(self):
        return [self.x, self.y]

    @staticmethod
    def _closest_point(array_coord, point):
        diff = array_coord - point
        return np.argmin(diff[:,0]**2 + diff[:,1]**2)


class SpectralImageVisualizer(SpectralImageVisualizerBase):
    def __init__(self, dset, figure=None, horizontal=True, **kwargs):
        super().__init__(dset, figure, horizontal, **kwargs)

        self.button = ipywidgets.widgets.Dropdown( options=[('Pixel Wise', 1), ('Units Wise', 2)],
                            value=1,
                            description='Image',
                            tooltip='How to plot spatial data: Pixel Wise (by px), Units wise (in given units)',
                            layout = ipywidgets.Layout(width='30%', height='50px',))

        self.button.observe(self._pw_uw, 'value') #pixel or unit wise

        widg = ipywidgets.HBox([self.button])
        #widg
        display(widg)

    def _pw_uw(self, event):
        pw_uw = event.new
        self.update_image(pw_uw)


    def update_image(self, event_value):
        #pixel wise or unit wise listener
        if event_value==1:
            self.axes[0].xaxis.set_ticks(ticks=list(np.linspace(self.extent[0], self.extent[1], 5)),
                                    labels=list(np.round(np.linspace(self.extent[0], self.extent[1], 5),2)))
            self.axes[0].yaxis.set_ticks(list(np.linspace(self.extent[2], self.extent[3], 5)),
                                    list(np.round(np.linspace(self.extent[2], self.extent[3], 5),1)))

            self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                     'px'))
            self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                         'px'))
        else:
            self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                     self.dset._axes[self.image_dims[0]].units))
            self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                            self.dset._axes[self.image_dims[1]].units))

            self.axes[0].xaxis.set_ticks(np.linspace(self.extent[0], self.extent[1], 5),
                                    list(np.round(np.linspace(self.extent_rd[0], self.extent_rd[1], 5), 2)),
                                         minor=False)

            self.axes[0].yaxis.set_ticks(np.linspace(self.extent[2], self.extent[3], 5),
                                    list(np.round(np.linspace(self.extent_rd[2], self.extent_rd[3], 5), 2)),
                                         minor=False)

            self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                        self.dset._axes[self.image_dims[0]].units))

            self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                            self.dset._axes[self.image_dims[1]].units))

            if self.dset._axes[self.image_dims[0]].units =='m':
                scaled_values_y = self.dset._axes[self.image_dims[1]].values*1E9
                scaled_values_x = self.dset._axes[self.image_dims[0]].values*1E9
                if scaled_values_x.mean() >=0.1 and  scaled_values_x.mean() <=1000:
                    self.axes[0].set_xticks(np.linspace(self.extent[0], self.extent[1], 5),
                                    list(np.round(np.linspace(scaled_values_x[0], scaled_values_x[-1], 5), 2)))
                    self.axes[0].set_yticks(np.linspace(self.extent[2], self.extent[3], 5),
                                    list(np.round(np.linspace(scaled_values_y[0], scaled_values_y[-1], 5), 2)))

                    self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[self.image_dims[0]].quantity,
                                                        'nm'))

                    self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[self.image_dims[1]].quantity,
                                                            'nm'))

        return

class PointCloudVisualizer(object):
    """
    Interactive point cloud visualization
    """
    def __init__(self, dset, base_image = None, figure=None, horizontal=True, **kwargs):

        if not isinstance(dset, sidpy.Dataset):
            raise TypeError('dset should be a sidpy.Dataset object')
        from scipy.interpolate import griddata
        from scipy.spatial import cKDTree
        import time

        self.dset = dset

        if self.dset.variance is not None:
            if self.dset.variance.shape != self.dset.shape:
                raise ValueError('Variance array must have the same dimensionality as the dataset')

        #kwargs parsing
        scale_bar = kwargs.pop('scale_bar', False)
        self.set_title = kwargs.pop('set_title', True)

        fig_args = dict()
        temp = kwargs.pop('figsize', None)
        if temp is not None:
            fig_args['figsize'] = temp

        #initial checks
        if len(dset.shape) < 2:
            raise TypeError('dataset must have at least two dimensions')
        if len(dset.shape) > 3:
            raise TypeError('dataset must have at most tree dimensions')
        if dset.point_cloud is None:
            raise TypeError(r'''must contain dataset.point_cloud attribute''')

        selection = []
        point_dims = []
        spectral_dim = []
        channel_dim = []

        for dim, axis in dset._axes.items():
            if axis.dimension_type == sidpy.DimensionType.POINT_CLOUD:
                selection.append(slice(None))
                point_dims.append(dim)
            elif axis.dimension_type == sidpy.DimensionType.SPECTRAL:
                selection.append(slice(0, 1))
                spectral_dim.append(dim)
            elif axis.dimension_type == sidpy.DimensionType.CHANNEL:
                channel_dim.append(dim)
            else:
                selection.append(slice(0, 1))

        #checking dimension types
        if len(channel_dim) >1:
            raise ValueError("We have more than one Channel Dimension, this won't work for the visualizer")
        if len(spectral_dim)>1:
            raise ValueError("We have more than one Spectral Dimension, this won't work for the visualizer...")
        if len(dset.shape)==3:
            if len(channel_dim)!=1:
                raise TypeError("We need one dimension with type CHANNEL \
                    for a spectral image plot for a 4D dataset")
        elif len(dset.shape)==2:
            if len(spectral_dim) != 1:
                raise TypeError("We need one dimension with dimension_type SPECTRAL \
                 to plot a spectra for a 3D dataset")

        #figure creation
        if figure is None:
            self.fig = plt.figure(**fig_args)
        else:
            self.fig = figure

        if horizontal:
            self.axes = self.fig.subplots(ncols=2)
        else:
            self.axes = self.fig.subplots(nrows=2, **fig_args)

        if self.set_title:
            self.fig.canvas.manager.set_window_title(self.dset.title)

        #pull base_image
        if base_image is not None:
            self.image, self.px_coord = self._base_image(base_image)
        else:
            if len(channel_dim) > 0:
                self.cloud= dset.mean(axis=(spectral_dim[0], channel_dim[0]))
            else:
                self.cloud = dset.mean(axis=(spectral_dim[0],))
            self.image, self.px_coord = self._mask_image()

        self.x = 0
        self.y = 0
        size_x, size_y = self.image.shape
        self.extent = [0, size_x, size_y, 0]
        self.rectangle = [0, size_x, 0, size_y]

        self.axes[0].imshow(self.image.T, extent=self.extent, **kwargs)
        self.axes[0].set_xticks(np.linspace(self.extent[0], self.extent[1], 5),)
        self.axes[0].set_xticklabels(np.round(np.linspace(self.extent[0], self.extent[1], 5),1))

        self.axes[0].set_yticks(np.linspace(self.extent[2], self.extent[3], 5),)
        self.axes[0].set_yticklabels(np.round(np.linspace(self.extent[2], self.extent[3], 5),1))
        self.axes[0].set_xlabel('{} [{}]'.format(self._quantity[0], 'px'))
        self.axes[0].set_ylabel('{} [{}]'.format(self._quantity[1], 'px'))

        self.axes[0].scatter(self.px_coord[:,0], self.px_coord[:,1], color='red', s=1)

        if scale_bar:
            self._scale_bar()

        #---spectral part----
        #find closest spectrum
        #self.tree = cKDTree(self.px_coord)
        _point_number = self.tree.query(np.array([self.x, self.y]))[1]
        self.sel_point = self.axes[0].scatter(self.px_coord[_point_number, 0], self.px_coord[_point_number, 1],
                             color='red', s=10, edgecolors='darkred')

        self.spectrum, self.variance = self.get_spectrum(_point_number)
        self.energy_axis = spectral_dim[0]
        if len(channel_dim)>0: self.channel_axis = channel_dim
        self.energy_scale = self.dset._axes[self.energy_axis].values

        self.spectrum_plot = [] #list is required for the case of several channels
        if len(self.spectrum.shape) > 1:
            for i in range(len(self.spectrum)):
                _spectrum_plot, = self.axes[1].plot(self.energy_scale, self.spectrum.compute()[i])
                self.spectrum_plot.append(_spectrum_plot)
        else:
            _spectrum_plot, = self.axes[1].plot(self.energy_scale, self.spectrum.compute())
            self.spectrum_plot.append(_spectrum_plot)

        self.fill_between = []
        if self.variance is not None:
            #3d - many curves
            if len(self.variance.shape) > 1:
                for i in range(len(self.variance)):
                    _fill_between = self.axes[1].fill_between(self.energy_scale,
                                              self.spectrum[i] - self.variance[i],
                                              self.spectrum[i] + self.variance[i],
                                              alpha=0.3, **kwargs)
                    self.fill_between.append(_fill_between)
            # 2d - one curve at each point
            else:
                _fill_between = self.axes[1].fill_between(self.energy_scale,
                                          self.spectrum - self.variance,
                                          self.spectrum + self.variance,
                                          alpha=0.3, **kwargs)
                self.fill_between.append(_fill_between)

        self.axes[1].set_title('point {}'.format(_point_number))
        self.axes[1].set_xlabel(self.dset.labels[self.energy_axis])
        self.axes[1].set_ylabel(self.dset.data_descriptor)
        self.axes[1].ticklabel_format(style='sci', scilimits=(-2, 3))
        self.fig.tight_layout()

        self.cid = self.axes[1].figure.canvas.mpl_connect('button_press_event', self._onclick)

        self.button = ipywidgets.widgets.Dropdown( options=[('Pixel Wise', 1), ('Units Wise', 2)],
                            value=1,
                            description='Image',
                            tooltip='How to plot spatial data: Pixel Wise (by px), Units wise (in given units)',
                            layout = ipywidgets.Layout(width='30%', height='50px',))

        self.button.observe(self._pw_uw, 'value') #pixel or unit wise

        self.fig.canvas.draw_idle()
        widg = ipywidgets.HBox([self.button])
        #widg
        display(widg)

    def _pw_uw(self, event):
        pw_uw = event.new
        self._update_image(pw_uw)

    def _update_image(self, event_value):
        # pixel wise or unit wise listener
        if 'spacial_units' in self.dset.point_cloud:
            _sp_units = self.dset.point_cloud['spacial_units']
            if isinstance(_sp_units, str):
                _sp_units = (_sp_units, _sp_units)
            elif not (isinstance(_sp_units, list) or isinstance(_sp_units, tuple)):
                raise ValueError('Spacial units in Dataset.point_cloud should be str or list, or tuple.')

        if 'quantity' in self.dset.point_cloud:
            _quantity = self.dset.point_cloud['quantity']
            if isinstance(_quantity, str):
                _quantity = (_quantity, _quantity)
            elif not (isinstance(_quantity, list) or isinstance(_quantity, tuple)):
                raise ValueError('Quantity in Dataset.point_cloud should be str or list, or tuple.')
        else:
            _quantity = ('distance', 'distance')

        if event_value == 1:
            self.axes[0].set_xticks(np.linspace(self.extent[0], self.extent[1], 5),)
            self.axes[0].set_xticklabels(np.round(np.linspace(self.extent[0], self.extent[1], 5), 1))

            self.axes[0].set_yticks(np.linspace(self.extent[2], self.extent[3], 5),)
            self.axes[0].set_yticklabels(np.round(np.linspace(self.extent[2], self.extent[3], 5), 1))

            self.axes[0].set_xlabel('{} [{}]'.format(_quantity[0], 'px'))
            self.axes[0].set_ylabel('{} [{}]'.format(_quantity[1], 'px'))
        else:
            self.axes[0].set_xticks(np.linspace(self.extent[0], self.extent[1], 5),)
            self.axes[0].set_xticklabels(np.round(np.linspace(self.real_extent[0], self.real_extent[1], 5), 2))

            self.axes[0].set_yticks(np.linspace(self.extent[2], self.extent[3], 5),)
            self.axes[0].set_yticklabels(np.round(np.linspace(self.real_extent[2], self.real_extent[3], 5), 2))

            if 'spacial_units' in self.dset.point_cloud:
                self.axes[0].set_xlabel('{} [{}]'.format(_quantity[0], _sp_units[0]))
                self.axes[0].set_ylabel('{} [{}]'.format(_quantity[1], _sp_units[1]))
            else:
                self.axes[0].set_xlabel('{}'.format(_quantity[0]))
                self.axes[0].set_ylabel('{}'.format(_quantity[1]))

    def _base_image(self, base_image):
        if not isinstance(base_image, sidpy.Dataset):
            raise TypeError('base_image should be a sidpy.Dataset object')
        if base_image.data_type.value != sidpy.DataType.IMAGE.value:
            raise TypeError(f'base_image expected to be IMAGE')
        if 'coordinates' in self.dset.point_cloud:
            coord = self.dset.point_cloud['coordinates']
        else:
            raise NotImplementedError('Datasets with data_type POINT_CLOUD must contain coordinates\
                                       in point_cloud attribute')

        image_dims = []
        selection = []

        for dim, axis in base_image._axes.items():
            if axis.dimension_type in [sidpy.DimensionType.SPATIAL, sidpy.DimensionType.RECIPROCAL]:
                image_dims.append(dim)
                selection.append(slice(None))
            else:
                selection.append(slice(0, 1))

        if len(image_dims) != 2:
            raise TypeError('We need two dimensions with dimension_type SPATIAL or RECIPROCAL to plot an image')

        self.image = base_image[tuple(selection)].squeeze()

        im_size = self.image.shape
        _x0, _x1, _y1, _y0 = base_image.get_extent(image_dims)
        _delta_x = _x1 - _x0
        _delta_y = _y1 - _y0

        self.real_extent = [_x0, _x1, _y1, _y0]
        self.dset.point_cloud['spacial_units'] = (base_image._axes[image_dims[0]].units,
                                                  base_image._axes[image_dims[1]].units)
        self.dset.point_cloud['quantity']      = (base_image._axes[image_dims[0]].quantity,
                                                  base_image._axes[image_dims[1]].quantity)

        _px_x = np.array((coord[:,0] - _x0)*im_size[1]/_delta_x).astype(int)
        _px_y = np.array((coord[:, 1] - _y0) * im_size[0]/_delta_y).astype(int)
        _px_coord = np.array([_px_x, _px_y]).T

        self.tree = scipy.spatial.cKDTree(_px_coord)

        return self.image, _px_coord


    def _scale_bar(self):
        from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
        self.axes[0].axis('off')
        extent = self.extent
        size_of_bar = int((extent[1] - extent[0]) / 10 + .5)
        if 'units' in self.dset.point_cloud:
            _units = self.dset.point_cloud['units']
        else:
            _units = 'px'

        if size_of_bar < 1:
            size_of_bar = 1
        scalebar = AnchoredSizeBar(self.axes[0].transData,
                                   size_of_bar, '{} {}'.format(size_of_bar,
                                                               _units),
                                   'lower left',
                                   pad=1,
                                   color='white',
                                   frameon=False,
                                   size_vertical=size_of_bar/5)

        self.axes[0].add_artist(scalebar)


    def _onclick(self, event):
        self.event = event
        if event.inaxes in [self.axes[0]]:
            self.x = round(event.xdata)
            self.y = round(event.ydata)
            _point_number = self.tree.query(np.array([self.x, self.y]))[1]
            self.spectrum, self.variance = self.get_spectrum(_point_number)
            if len(self.spectrum.shape) > 1:
                for i in range(len(self.spectrum)):
                    self.spectrum_plot[i].set_data(self.energy_scale, self.spectrum.compute()[i])
            else:
                self.spectrum_plot[0].set_data(self.energy_scale, self.spectrum.compute())

            if self.variance is not None:
                # 3d - many curves
                if len(self.variance.shape) > 1:
                    for i in range(len(self.variance)):
                        _c = self.fill_between[i].get_facecolor()[0]
                        self.fill_between[i].remove()
                        self.fill_between[i] = self.axes[1].fill_between(self.energy_scale,
                                              self.spectrum[i] - self.variance[i],
                                              self.spectrum[i] + self.variance[i],
                                              color= _c)
                else:
                    _c = self.fill_between[0].get_facecolor()[0]
                    self.fill_between[0].remove()
                    self.fill_between[0] = self.axes[1].fill_between(self.energy_scale,
                                                                     self.spectrum - self.variance,
                                                                     self.spectrum + self.variance,
                                                                     color=_c)

            self.axes[1].set_title('point {}'.format(_point_number))
            self.sel_point.set_offsets(np.column_stack((self.px_coord[_point_number, 0],
                                                        self.px_coord[_point_number, 1])))

            self.fig.canvas.draw_idle()
        else:
            if event.dblclick:
                bottom = float(self.spectrum.min())
                if bottom < 0:
                    bottom *= 1.02
                else:
                    bottom *= 0.98
                top = float(self.spectrum.max())
                if top > 0:
                    top *= 1.02
                else:
                    top *= 0.98

                self.axes[1].set_ylim(bottom=bottom, top=top)

    def get_spectrum(self, point_number):
        '''
        Getting the spectrum by the point number in the point cloud.
        Parameters
        ----------
        point_number: int

        Returns
        -------
        self.spectrum: sidpy.array
        '''
        selection = []
        for dim, axis in self.dset._axes.items():
            if axis.dimension_type == sidpy.DimensionType.POINT_CLOUD:
                selection.append(point_number)
            elif axis.dimension_type == sidpy.DimensionType.SPECTRAL:
                selection.append(slice(None))
            elif axis.dimension_type == sidpy.DimensionType.CHANNEL:
                selection.append(slice(None))
            else:
                selection.append(slice(0, 1))

        self.spectrum = self.dset[tuple(selection)].squeeze()
        if self.dset.variance is not None:
            self.variance = self.dset.variance[tuple(selection)].squeeze()
        else:
            self.variance = None
        return self.spectrum, self.variance

    def _mask_image(self):
        '''
        Griddata transformation of the unstructured point cloud to the numpy 2D array

        Returns
        -------
        2D np.array - image data
        2D np.array - coordinate data
        '''

        if 'coordinates' in self.dset.point_cloud:
            coord = self.dset.point_cloud['coordinates']
        else:
            raise NotImplementedError('Datasets with data_type POINT_CLOUD must contain coordinates\
                                       in point_cloud attribute')

        # minimal image size in 50x50px or equal to the number of point for dimensions
        im_size = max(50, coord.shape[0])

        _x0, _x1 = np.min(coord, axis=0)[0], np.max(coord, axis=0)[0]
        _y0, _y1 = np.min(coord, axis=0)[1], np.max(coord, axis=0)[1]
        _delta_x = _x1 - _x0
        _delta_y = _y1 - _y0

        #to extend filed of view
        _x0, _x1 = _x0 - 0.05*_delta_x, _x1 + 0.05*_delta_x
        _y0, _y1 = _y0 - 0.05*_delta_y, _y1 + 0.05 * _delta_y
        self.real_extent = [_x0, _x1, _y1, _y0]

        _px_x = np.array((coord[:,0] - _x0)*im_size/(_x1-_x0)).astype(int)
        _px_y = np.array((coord[:, 1] - _y0) * im_size/ (_y1-_y0)).astype(int)
        _px_coord = np.array([_px_x, _px_y]).T
        self.tree = scipy.spatial.cKDTree(_px_coord)
        grid_x, grid_y = np.mgrid[0:im_size, 0:im_size]
        mask = scipy.interpolat.griddata(_px_coord, self.cloud, (grid_x, grid_y), method='nearest')
        return mask, _px_coord

    def get_xy(self):
        return [self.x, self.y]

class FourDimImageVisualizer(object):

    """
    ### Interactive 4D imaging plot

    Either you specify only two spatial dimensions or you specify
    scan_x and scan_y
    image_4d_x, image_4d_y

    If none of the keywords are specified, it is assumed that the order is slowest to fastest dimension.

    """

    def __init__(self, dset, figure=None, horizontal=True, **kwargs):

        if not isinstance(dset, sidpy.Dataset):
            raise TypeError('dset should be a sidpy.Dataset object')
        scale_bar = kwargs.pop('scale_bar', False)
        colorbar = kwargs.pop('colorbar', True)
        self.set_title = kwargs.pop('set_title', True)
        
        fig_args = dict()
        temp = kwargs.pop('figsize', None)
        if temp is not None:
            fig_args['figsize'] = temp

        if figure is None:
            self.fig = plt.figure(**fig_args)
        else:
            self.fig = figure

        if len(dset.shape) < 4:
            raise TypeError('dataset must have at least four dimensions')

        # Find scan and 4D_image dimension

        scan_x = kwargs.pop('scan_x', None)
        scan_y = kwargs.pop('scan_y', None)

        image_x = kwargs.pop('image_4d_x', None)
        image_y = kwargs.pop('image_4d_y', None)
        self.gamma = kwargs.pop('gamma', False)
        for dim, axis in dset._axes.items():
            if axis.dimension_type in [sidpy.DimensionType.SPATIAL]:
                if scan_y is None:
                    scan_y = dim
                elif scan_x is None:
                    scan_x = dim

        # We assume slow scan first order
        if scan_y is None or scan_x is None:
            scan_y = 0
            scan_x = 1

        if image_y is None:
            for dim in range(4):
                if dim not in [scan_x, scan_y]:
                    image_y = dim
                    break
        if image_x is None:
            for dim in range(4):
                if dim not in [image_y, scan_x, scan_y]:
                    image_x = dim
                    break

        image_dims = [scan_x, scan_y]
        dims_4d = [image_x, image_y]

        if len(image_dims) != 2:
            raise TypeError('We need two dimensions with dimension_type SPATIAL: to plot an image')

        if len(dims_4d) != 2:
            raise TypeError('We need two dimension with dimension_type other than spatial for a 4D image plot')

        self.horizontal = horizontal
        self.x = 0
        self.y = 0
        self.bin_x = 1
        self.bin_y = 1

        image_dims = [scan_x, scan_y]

        size_x = dset.shape[image_dims[0]]
        size_y = dset.shape[image_dims[1]]

        self.dset = dset

        self.extent = [0, size_x, size_y, 0]
        self.rectangle = [0, size_x, 0, size_y]
        self.scaleX = 1.0
        self.scaleY = 1.0
        self.analysis = []
        self.plot_legend = False

        self.image_dims = image_dims
        self.dims_4d = dims_4d
        if is_complex_dtype(dset.dtype):
            number_of_plots = 3
        else:
            number_of_plots = 2
        self.number_of_plots = number_of_plots

        if horizontal:
            self.axes = self.fig.subplots(ncols=number_of_plots)
        else:
            self.axes = self.fig.subplots(nrows=number_of_plots, **fig_args)

        if self.set_title:
            self.fig.canvas.manager.set_window_title(self.dset.title)
        self.image = np.array(dset).mean(axis=tuple(dims_4d))
        if is_complex_dtype(dset.dtype):
            self.image = np.abs(np.array(dset)).mean(axis=tuple(dims_4d))

        self.axes[0].imshow(self.image.T, extent=self.dset.get_extent(self.image_dims), **kwargs)
        #if horizontal:
        self.axes[0].set_xlabel('{} [{}]'.format(self.dset._axes[image_dims[0]].quantity,
        self.dset._axes[image_dims[0]].units))
        #else:
        self.axes[0].set_ylabel('{} [{}]'.format(self.dset._axes[image_dims[1]].quantity,
        self.dset._axes[image_dims[1]].units))
        self.axes[0].set_aspect('equal')

        # self.rect = patches.Rectangle((0,0),1,1,linewidth=1,edgecolor='r',facecolor='red', alpha = 0.2)
        self.rect = patches.Rectangle((0, 0), self.bin_x, self.bin_y, linewidth=1, edgecolor='r',
                                      facecolor='red', alpha=0.2)

        self.axes[0].add_patch(self.rect)
        self.intensity_scale = 1.
        self.image_4d = self.get_image_4d()
        if is_complex_dtype(dset.dtype):    
            self.image_4d = np.abs(self.image_4d)
        if self.gamma:
            self.image_4d = np.log(1+self.image_4d)
        
        self.reciprocal_extent = None
        if len(self.dset.get_extent(self.dset.get_spectrum_dims()))==4:
            self.reciprocal_extent = self.dset.get_extent(self.dset.get_spectrum_dims())

        self.axes[1].imshow(self.image_4d, extent = self.reciprocal_extent)

        if self.set_title:
            self.axes[1].set_title('set {}, {}'.format(self.x, self.y))
        self.xlabel = self.dset.labels[self.dims_4d[0]]
        self.ylabel = self.dset.labels[self.dims_4d[1]]
        self.axes[1].set_xlabel(self.xlabel)  # + x_suffix)
        self.axes[1].set_ylabel(self.ylabel)
        self.axes[1].ticklabel_format(style='sci', scilimits=(-2, 3))
        if is_complex_dtype(dset.dtype):
            self.axes[2].imshow(np.angle(np.array(self.image_4d)))
            if self.set_title:
                self.axes[1].set_title('power {}, {}'.format(self.x, self.y))
                self.axes[2].set_title('phase {}, {}'.format(self.x, self.y))
            self.axes[2].set_xlabel(self.xlabel)  # + x_suffix)
            self.axes[2].set_ylabel(self.ylabel)
            self.axes[2].ticklabel_format(style='sci', scilimits=(-2, 3))
            
        self.fig.tight_layout()
        self.cid = self.axes[1].figure.canvas.mpl_connect('button_press_event', self._onclick)

        self.fig.canvas.draw_idle()

    def set_bin(self, bin_xy):

        old_bin_x = self.bin_x
        old_bin_y = self.bin_y
        if isinstance(bin_xy, list):

            self.bin_x = int(bin_xy[0])
            self.bin_y = int(bin_xy[1])

        else:
            self.bin_x = int(bin_xy)
            self.bin_y = int(bin_xy)

        if self.bin_x > self.dset.shape[self.image_dims[0]]:
            self.bin_x = self.dset.shape[self.image_dims[0]]
        if self.bin_y > self.dset.shape[self.image_dims[1]]:
            self.bin_y = self.dset.shape[self.image_dims[1]]

        self.rect.set_width(self.rect.get_width() * self.bin_x / old_bin_x)
        self.rect.set_height((self.rect.get_height() * self.bin_y / old_bin_y))
        if self.x + self.bin_x > self.dset.shape[self.image_dims[0]]:
            self.x = self.dset.shape[0] - self.bin_x
        if self.y + self.bin_y > self.dset.shape[self.image_dims[1]]:
            self.y = self.dset.shape[1] - self.bin_y

        self.rect.set_xy([self.x * self.rect.get_width() / self.bin_x + self.rectangle[0],
                          self.y * self.rect.get_height() / self.bin_y + self.rectangle[2]])
        self._update()

    def get_image_4d(self):
        from sidpy import DimensionType

        if self.x > self.dset.shape[self.image_dims[0]] - self.bin_x:
            self.x = self.dset.shape[self.image_dims[0]] - self.bin_x
        if self.y > self.dset.shape[self.image_dims[1]] - self.bin_y:
            self.y = self.dset.shape[self.image_dims[1]] - self.bin_y
        selection = []

        for dim, axis in self.dset._axes.items():
            # print(dim, axis.dimension_type)
            if dim == self.image_dims[0]:
                selection.append(slice(self.x, self.x + self.bin_x))
            elif dim == self.image_dims[1]:
                selection.append(slice(self.y, self.y + self.bin_y))

            elif dim in self.dims_4d:
                selection.append(slice(None))
            else:
                selection.append(slice(0, 1))

        self.image_4d = self.dset[tuple(selection)].mean(axis=tuple(self.image_dims))
        # * self.intensity_scale[self.x,self.y]

        return self.image_4d.squeeze()

    def _onclick(self, event):
        self.event = event
        if event.inaxes in [self.axes[0]]:
            x = int(event.xdata)
            y = int(event.ydata)

            x = int(x - self.rectangle[0])
            y = int(y - self.rectangle[2])

            if x >= 0 and y >= 0:
                if x <= self.rectangle[1] and y <= self.rectangle[3]:
                    self.x = int(x / (self.rect.get_width() / self.bin_x))
                    self.y = int(y / (self.rect.get_height() / self.bin_y))

                    if self.x + self.bin_x > self.dset.shape[self.image_dims[0]]:
                        self.x = self.dset.shape[self.image_dims[0]] - self.bin_x
                    if self.y + self.bin_y > self.dset.shape[self.image_dims[1]]:
                        self.y = self.dset.shape[self.image_dims[1]] - self.bin_y

                    self.rect.set_xy([self.x * self.rect.get_width() / self.bin_x + self.rectangle[0],
                                      self.y * self.rect.get_height() / self.bin_y + self.rectangle[2]])
        self._update()

    def _update(self, ev=None):

        xlim = self.axes[1].get_xlim()
        ylim = self.axes[1].get_ylim()
        self.axes[1].clear()
        self.get_image_4d()
        if is_complex_dtype(self.dset.dtype):
            self.axes[2].clear()
            self.image_4d = np.abs(self.image_4d)
            self.axes[2].imshow(np.angle(self.image_4d))
            if self.set_title:
                self.axes[1].set_title('power {}, {}'.format(self.x, self.y))
                self.axes[2].set_title('phase {}, {}'.format(self.x, self.y))
            self.axes[2].set_xlabel(self.xlabel)  # + x_suffix)
            self.axes[2].set_ylabel(self.ylabel)
            self.axes[2].ticklabel_format(style='sci', scilimits=(-2, 3))
        else:
            if self.set_title:
                self.axes[1].set_title('set {}, {}'.format(self.x, self.y))
        if self.gamma:
            self.image_4d = np.log(1+self.image_4d)
        self.axes[1].imshow(self.image_4d,
            extent = self.reciprocal_extent)

        self.axes[1].set_xlim(xlim)
        self.axes[1].set_ylim(ylim)
        self.axes[1].set_xlabel(self.xlabel)
        self.axes[1].set_ylabel(self.ylabel)

        self.fig.canvas.draw_idle()

    def set_legend(self, set_legend):
        self.plot_legend = set_legend

    def get_xy(self):
        return [self.x, self.y]


class ComplexSpectralImageVisualizer(object):
    """
    ### Interactive spectrum imaging plot for Complex Data
    ## 4D and complex data also works

    """

    def __init__(self, dset, figure=None, horizontal=True, **kwargs):

        if not isinstance(dset, sidpy.Dataset):
            raise TypeError('dset should be a sidpy.Dataset object')
        
        scale_bar = kwargs.pop('scale_bar', False)
        colorbar = kwargs.pop('colorbar', True)
        self.set_title = kwargs.pop('set_title', True)
        
        fig_args = dict()
        temp = kwargs.pop('figsize', None)
        if temp is not None:
            fig_args['figsize'] = temp

        if figure is None:
            self.fig = plt.figure(**fig_args)
        else:
            self.fig = figure

        if len(dset.shape) > 4:
            raise TypeError('dataset must have four dimensions at max')
        if 'complex' not in dset.dtype.name:
            raise TypeError('This visualizer is only for Complex Data, data type is {}'.format(dset.dtype))
        
        # We need one stack dim and two image dimes as lists in dictionary
        selection = []
        image_dims = []
        spectral_dim = []
        channel_dim = []
        for dim, axis in dset._axes.items():
            if axis.dimension_type in [sidpy.DimensionType.SPATIAL, sidpy.DimensionType.RECIPROCAL]:
                selection.append(slice(None))
                image_dims.append(dim)
            elif axis.dimension_type == sidpy.DimensionType.SPECTRAL:
                selection.append(slice(0, 1))
                spectral_dim.append(dim)
            elif axis.dimension_type == sidpy.DimensionType.CHANNEL:
                channel_dim.append(dim)
            else:
                selection.append(slice(0, 1))
        
        if len(image_dims) != 2:
            raise TypeError('We need two dimensions with dimension_type SPATIAL: to plot an image')
        if len(channel_dim) >1:
            raise ValueError("We have more than one Channel Dimension, this won't work for the visualizer")
        if len(spectral_dim)>1:
            raise ValueError("We have more than one Spectral Dimension, this won't work for the visualizer...")

        if len(dset.shape)==4:
            if len(channel_dim)!=1:
                raise TypeError("We need one dimension with type CHANNEL \
                    for a spectral image plot for a 4D dataset")
        elif len(dset.shape)==3:
            if len(spectral_dim) != 1:
                raise TypeError("We need one dimension with dimension_type SPECTRAL \
                 to plot a spectra for a 3D dataset")

        self.horizontal = horizontal
        self.x = 0
        self.y = 0
        self.bin_x = 1
        self.bin_y = 1

        size_x = dset.shape[image_dims[0]]
        size_y = dset.shape[image_dims[1]]

        self.dset = dset
        self.energy_axis = spectral_dim[0]
        if len(channel_dim)>0: self.channel_axis = channel_dim
        self.energy_scale = dset._axes[self.energy_axis].values
        self.extent = [0, size_x, size_y, 0]
        self.rectangle = [0, size_x, 0, size_y]
        self.scaleX = 1.0
        self.scaleY = 1.0
        self.analysis = []
        self.plot_legend = False
        self.ri_ap = 'Real and Imaginary' #real/imaginary of amplitude/phase plotting

        self.image_dims = image_dims
        self.spec_dim = spectral_dim[0]

        if horizontal:
            self.axes = self.fig.subplots(ncols=3)
        else:
            self.axes = self.fig.subplots(nrows=3, **fig_args)

        if self.set_title:
            self.fig.canvas.manager.set_window_title(self.dset.title)

        if len(channel_dim)>0:
            self.image = dset.mean(axis=(spectral_dim[0],channel_dim[0]))
        else:
            self.image = dset.mean(axis=(spectral_dim[0]))

        if 1 in self.dset.shape:
            self.image = dset.squeeze()
            self.axes[0].set_aspect('auto')
        else:
            self.axes[0].set_aspect('equal')

        #self.axes[0].imshow(np.abs(self.image.T), extent=self.extent, **kwargs)# throwing an error
        self.axes[0].imshow(np.abs(np.array(self.image)).T, extent=self.extent, **kwargs)
        if horizontal:
            self.axes[0].set_xlabel('{} [pixels]'.format(self.dset._axes[image_dims[0]].quantity))
        else:
            self.axes[0].set_ylabel('{} [pixels]'.format(self.dset._axes[image_dims[1]].quantity))

        if 1 in self.dset.shape:
            self.axes[0].set_aspect('auto')
            self.axes[0].get_yaxis().set_visible(False)
        else:
            self.axes[0].set_aspect('equal')

        self.rect = patches.Rectangle((0, 0), self.bin_x, self.bin_y, linewidth=1, edgecolor='r',
                                      facecolor='red', alpha=0.2)

        self.axes[0].add_patch(self.rect)
        self.intensity_scale = 1.
        self.spectrum = self.get_spectrum()
        if len(self.energy_scale)!=self.spectrum.shape[0]:
            self.spectrum = self.spectrum.T
        self.axes[1].plot(self.energy_scale, np.real(self.spectrum.compute()), label = 'Real')
        self.axes[2].plot(self.energy_scale, np.imag(self.spectrum.compute()), label = 'Imaginary')
        for ax_ind in [1,2]:
            self.axes[ax_ind].set_title('spectrum {}, {}'.format(self.x, self.y))
            self.xlabel = self.dset.labels[self.spec_dim]
            self.ylabel = self.dset.data_descriptor
            self.axes[ax_ind].set_xlabel(self.dset.labels[self.spec_dim])  # + x_suffix)
            self.axes[ax_ind].set_ylabel(self.dset.data_descriptor)
            self.axes[ax_ind].ticklabel_format(style='sci', scilimits=(-2, 3))
            leg = self.axes[ax_ind].legend(loc = 'best')
            leg.get_frame().set_linewidth(0.0)
        self.fig.tight_layout()
        self.cid = self.axes[1].figure.canvas.mpl_connect('button_press_event', self._onclick)
        import ipywidgets as iwgt
        self.button = iwgt.widgets.Dropdown(options=['Real and Imaginary', 'Amplitude and Phase'],
                                description='Plot',
                                disabled=False,
                                tooltip='How to plot complex data')

        self.button.observe(self._ri_ap, 'value') #real/imag or amp/phase

        widg = ipywidgets.HBox([self.button])
        display(widg)

        self.fig.canvas.draw_idle()

    def _ri_ap(self, event):
        self.ri_ap = event.new
        self._update()

    def set_bin(self, bin_xy):

        old_bin_x = self.bin_x
        old_bin_y = self.bin_y
        if isinstance(bin_xy, list):

            self.bin_x = int(bin_xy[0])
            self.bin_y = int(bin_xy[1])

        else:
            self.bin_x = int(bin_xy)
            self.bin_y = int(bin_xy)

        if self.bin_x > self.dset.shape[self.image_dims[0]]:
            self.bin_x = self.dset.shape[self.image_dims[0]]
        if self.bin_y > self.dset.shape[self.image_dims[1]]:
            self.bin_y = self.dset.shape[self.image_dims[1]]

        self.rect.set_width(self.rect.get_width() * self.bin_x / old_bin_x)
        self.rect.set_height((self.rect.get_height() * self.bin_y / old_bin_y))
        if self.x + self.bin_x > self.dset.shape[self.image_dims[0]]:
            self.x = self.dset.shape[0] - self.bin_x
        if self.y + self.bin_y > self.dset.shape[self.image_dims[1]]:
            self.y = self.dset.shape[1] - self.bin_y

        self.rect.set_xy([self.x * self.rect.get_width() / self.bin_x + self.rectangle[0],
                          self.y * self.rect.get_height() / self.bin_y + self.rectangle[2]])
        self._update()

    def get_spectrum(self):

        if self.x > self.dset.shape[self.image_dims[0]] - self.bin_x:
            self.x = self.dset.shape[self.image_dims[0]] - self.bin_x
        if self.y > self.dset.shape[self.image_dims[1]] - self.bin_y:
            self.y = self.dset.shape[self.image_dims[1]] - self.bin_y
        selection = []

        for dim, axis in self.dset._axes.items():
            # print(dim, axis.dimension_type)
            if axis.dimension_type == sidpy.DimensionType.SPATIAL:
                if dim == self.image_dims[0]:
                    selection.append(slice(self.x, self.x + self.bin_x))
                else:
                    selection.append(slice(self.y, self.y + self.bin_y))

            elif axis.dimension_type == sidpy.DimensionType.SPECTRAL:
                selection.append(slice(None))
            elif axis.dimension_type == sidpy.DimensionType.CHANNEL:
                selection.append(slice(None))
            else:
                selection.append(slice(0, 1))
        
        self.spectrum = self.dset[tuple(selection)].mean(axis=tuple(self.image_dims))
        
        # * self.intensity_scale[self.x,self.y]
        return self.spectrum.squeeze()

    def _onclick(self, event):
        self.event = event
        if event.inaxes in [self.axes[0]]:
            x = int(event.xdata)
            y = int(event.ydata)

            x = int(x - self.rectangle[0])
            y = int(y - self.rectangle[2])

            if x >= 0 and y >= 0:
                if x <= self.rectangle[1] and y <= self.rectangle[3]:
                    self.x = int(x / (self.rect.get_width() / self.bin_x))
                    self.y = int(y / (self.rect.get_height() / self.bin_y))

                    if self.x + self.bin_x > self.dset.shape[self.image_dims[0]]:
                        self.x = self.dset.shape[self.image_dims[0]] - self.bin_x
                    if self.y + self.bin_y > self.dset.shape[self.image_dims[1]]:
                        self.y = self.dset.shape[self.image_dims[1]] - self.bin_y

                    self.rect.set_xy([self.x * self.rect.get_width() / self.bin_x + self.rectangle[0],
                                      self.y * self.rect.get_height() / self.bin_y + self.rectangle[2]])
            self._update()
        else:
            if event.dblclick:
                bottom = float(self.spectrum.min())
                if bottom < 0:
                    bottom *= 1.02
                else:
                    bottom *= 0.98
                top = float(self.spectrum.max())
                if top > 0:
                    top *= 1.02
                else:
                    top *= 0.98

                self.axes[1].set_ylim(bottom=bottom, top=top)

    def _update(self, ev=None):

        xlim_ax1 = self.axes[1].get_xlim()
        ylim_ax1 = self.axes[1].get_ylim()
        xlim_ax2 = self.axes[2].get_xlim()
        ylim_ax2 = self.axes[2].get_ylim()
        
        xlims = [xlim_ax1,xlim_ax2]
        ylims = [ylim_ax1, ylim_ax2]

        self.axes[1].clear()
        self.axes[2].clear()
        self.get_spectrum()
        if len(self.energy_scale)!=self.spectrum.shape[0]:
            self.spectrum = self.spectrum
        
        if self.ri_ap == 'Real and Imaginary':
            self.axes[1].plot(self.energy_scale, np.real(self.spectrum.compute()), label='Real')
            self.axes[2].plot(self.energy_scale, np.imag(self.spectrum.compute()), label='Imaginary')
        else:
            self.axes[1].plot(self.energy_scale, np.abs(self.spectrum.compute()), label='Amplitude')
            self.axes[2].plot(self.energy_scale, np.angle(self.spectrum.compute()), label='Phase')

        for ind,ax_ind in enumerate([1,2]):
            if self.set_title:
                self.axes[ax_ind].set_title('spectrum {}, {}'.format(self.x, self.y))
            
            self.axes[ax_ind].set_xlim(xlims[ind])
            self.axes[ax_ind].set_xlabel(self.xlabel)
            self.axes[ax_ind].set_ylabel(self.ylabel)
            leg = self.axes[ax_ind].legend(loc = 'best')
            leg.get_frame().set_linewidth(0.0)
        self.fig.canvas.draw_idle()
        self.fig.tight_layout()

    def set_legend(self, set_legend):
        self.plot_legend = set_legend

    def get_xy(self):
        return [self.x, self.y]


class SpectralImageFitVisualizer(SpectralImageVisualizer):
    
    def __init__(self, original_dataset, fit_dataset, figure=None, horizontal=True):
        '''
        Visualizer for spectral image datasets, fit by the Sidpy Fitter
        This class is called by Sidpy Fitter for visualizing the raw/fit dataset interactively.

        Inputs:
            - original_dataset: sidpy.Dataset containing the raw data
            - fit_dataset: sidpy.Dataset with the fitted data. This is returned by the 
            Sidpy Fitter after functional fitting.
            - figure: (Optional, default None) - handle to existing figure
            - horiziontal: (Optional, default True) - whether spectrum should be plotted horizontally
        '''

        super().__init__(original_dataset, figure, horizontal)
       
        self.fit_dset = fit_dataset
        self.axes[1].clear()
        self.get_fit_spectrum()
        self.axes[1].plot(self.energy_scale, self.spectrum, 'bo')
        self.axes[1].plot(self.energy_scale, self.fit_spectrum, 'r-')
        
    def get_fit_spectrum(self):

        if self.x > self.dset.shape[self.image_dims[0]] - self.bin_x:
            self.x = self.dset.shape[self.image_dims[0]] - self.bin_x
        if self.y > self.dset.shape[self.image_dims[1]] - self.bin_y:
            self.y = self.dset.shape[self.image_dims[1]] - self.bin_y
        selection = []

        for dim, axis in self.dset._axes.items():
            if axis.dimension_type == sidpy.DimensionType.SPATIAL:
                if dim == self.image_dims[0]:
                    selection.append(slice(self.x, self.x + self.bin_x))
                else:
                    selection.append(slice(self.y, self.y + self.bin_y))

            elif axis.dimension_type == sidpy.DimensionType.SPECTRAL:
                selection.append(slice(None))
            else:
                selection.append(slice(0, 1))

        self.spectrum = np.array(self.dset[tuple(selection)].mean(axis=tuple(self.image_dims)))
        self.fit_spectrum = np.array(self.fit_dset[tuple(selection)].mean(axis=tuple(self.image_dims)))
        # * self.intensity_scale[self.x,self.y]
        
        return self.fit_spectrum.squeeze(), self.spectrum.squeeze()
        
        
    def _update(self, ev=None):

        xlim = self.axes[1].get_xlim()
        ylim = self.axes[1].get_ylim()
        self.axes[1].clear()
        self.get_fit_spectrum()
        
        self.axes[1].plot(self.energy_scale, self.spectrum, 'bo', label='experiment')
        self.axes[1].plot(self.energy_scale, self.fit_spectrum, 'r-', label='fit')
        
        if self.set_title:
            self.axes[1].set_title('spectrum {}, {}'.format(self.x, self.y))

        self.axes[1].set_xlim(xlim)
        #self.axes[1].set_ylim(ylim)
        self.axes[1].set_xlabel(self.xlabel)
        self.axes[1].set_ylabel(self.ylabel)

        self.fig.canvas.draw_idle()
        
        
