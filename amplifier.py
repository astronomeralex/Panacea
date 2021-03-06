#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Amplifier Class
-----------
To be used in conjuction with IFU reduction code, Panacea


"""

from __future__ import (division, print_function, absolute_import,
                        unicode_literals)

from distutils.dir_util import mkpath
from utils import biweight_location, biweight_filter
from astropy.io import fits
import os.path as op
import numpy as np
import os
import sys
import re
import glob
import time
import cPickle as pickle
from fiber_utils import get_trace_from_image, fit_fibermodel_nonparametric
from fiber_utils import get_norm_nonparametric_fast, check_fiber_trace
from fiber_utils import calculate_wavelength_chi2, get_model_image
from fiber_utils import check_fiber_profile, check_wavelength_fit
from fiber import Fiber
import cosmics
from datetime import datetime


__all__ = ["Amplifier"]

class Amplifier:
    def __init__(self, filename, path, name=None, refit=False, calpath=None, 
                 skypath=None, debug=False, darkpath=None, biaspath=None, 
                 virusconfig=None, dark_mult=1., bias_mult=0., 
                 use_pixelflat=True, specname=None, fdist=2., fdist_ref=4., 
                 check_trace=True, calculate_shift=False, trace_poly_order=3,
                 fibmodel_poly_order=3, use_default_fibmodel=False, 
                 fibmodel_nbins=15, make_fib_ind_plots=False, 
                 check_fibermodel=False, fsize=8., sigma=2.5, power=2.5,
                 fiber_group=8, col_group=48, mask=None, wave_nbins=21, 
                 wave_order=3, default_fib=0, init_lims=None, 
                 interactive=False, check_wave=False,filt_size_ind=21, 
                 filt_size_agg=51, filt_size_final=51, filt_size_sky=51,
                 col_frac = 0.47, use_trace_ref=False, fiber_date=None,
                 cont_smooth=25, make_residual=True, do_cont_sub=True,
                 make_skyframe=True, wave_res=1.9):
        ''' 
        Initialize class
        ----------------
        :param filename:
            Filename for the raw data (which is just a single amplifier)
        :param path:
            The output path where to save the amplifier class and Fiber class
        :param refit:
            If set to yes, then nearly all attributes are refit.
            Specifically:
                1) Trace
                2) Fibermodel
                3) Wavelength Solution
                4) Fiber to Fiber Normalization for the amplifier in question
        :param calpath:
            This parameter sets the file path that points to the compressed
            Fiber Class files of previously reduced calibration frames.  
            This path is used to load trace, wavelength solution, fibermodel, 
            and fiber_to_fiber properties.
        :param skypath:
            This parameter sets the file path that points to the compressed
            Fiber Class files of previously reduced sky frames.  This path
            is used to load "sky_spectrum" properties.
        :param debug:
            This is used to print out run times for different stages.  In many
            ways this parameter is ever changing for various debugging 
            purposes.
        :param darkpath:
            This path is used to point to the library containing dark current
            images for each amplifier.
        :param biaspath:
            This path is used to point to the library containing bias images
            for each amplifier.
        :param virusconfig:
            This path points to a more general library of PixelFlats, IFUcen
            Files, Fplane files, and solar/twighlight spectra.
        :param dark_mult:
            This value is used to multiply the dark image before subtraction.
        :param bias_mult:
            This value is used to multiply the bias image before subtraction.
        :param use_pixelflat:
            A boolean for correcting the pixel to pixel variations.
        :param specname:
            Base filename for loading the solar/twighlight spectrum used
            in wavelength calibration.
        :param fdist:
            This parameter sets the distance allowable to match fiber
            centroid measurments for neighboring columns.  Ideal values are
            generous enough for glitches and gaps and yet small enough to not 
            jump to neighboring fibers.  
        :param fdist_ref:
            This parameter sets the distance allowable to match fiber
            centroid measurments for reference fibers.
        :param check_trace:
            Plot trace images at the end.  Good for post checks.
        :param calculate_shift:
            Calculate the shift between calibration files and new trace 
            measurement.
        :param trace_poly_order:
            Not in use now, but remains for possible future use.
        :param fibmodel_poly_order:
            This parameter is not used anymore but remains for flexibility if
            it is useful again.
        :param use_default_fibmodel:
            If true, no fit is performed and instead the default fiber model
            is used.  The default profile is a gauss-hermite exponential and is
            defined by "bins", "fsize", "sigma", and "power". 
        :param fibmodel_nbins:
            The number of bins (+2) used to define the fiber profile.
        :param make_fib_ind_plots:
            If True, plots for each image stamp that is fit.  Produces 
            number of fibers times col_group images.  Typically 112x48 = 5376.
            This also takes awhile to save all of these images.
        :param check_fibermodel:
            If True, a summary plot is produced of the fibermodel fit for the 
            top/bottom/middle of the amplifier in fibers and columns 
            (3x3 plot).
        :param fsize:
            The pixel size from the center of the trace over which the 
            fibermodel is defined. In other words: [trace-fsize:trace+fsize].
        :param sigma:
            The sigma parameter for the gauss-hermite exponential for the 
            initial/default fibermodel.  This model is used to defining the
            binning of the empirical fibermodel through the CDF of the 
            second derivative.
        :param power:
            The power parameter for the gauss-hermite exponential for the 
            initial/default fibermodel.
        :param fiber_group:
            Total number of fibers used to constrain the profile at one time.
        :param col_group:
            Total number of columns used to constrain the profile at one time.
        :param mask:
            Used for masking pixels and avoids them in the spectral extraction.
        :param wave_nbins:
            Number of bins used across the wavelength range to fit
            linear solutions.
        :param wave_order:
            Polynomial order for fitting the wavelength solution.
        :param default_fib:
            The first fiber to fit for the wavelength solution.
        :param init_lims:
            List or tuple of two values for the starting and finishing 
            wavelengths for the amplifier.  General values are fine.  In
            other words, [3500,5500] for VIRUS.
        :param interactive:
            The first fiber wavelength solution fit is interactive.
        :param check_wave:
            Plots the wavelength solution in a 3x3 grid covering the 
            top/middle/bottom fibers and columns. 
        :param filt_size_ind:
            Biweight filter size for individual spectra
        :param filt_size_agg:
            Biweight filter size for the master spectrum
        :param filt_size_final:
            Biweight filter size for fiber to fiber
        :param filt_size_sky:
            Biweigth filter size for the master sky
        :param col_frac:
            Column that is this fraction through the image.
            In other words, col = int(num_cols * col_frac)
        :param use_trace_ref:
            This is a boolean variable that sets whether the fibers found
            are compared with reference fibers and define dead fibers if
            there are missing fibers in the search.
        :param fiber_date:
            The date on which the fiber reference is located.
            
        :init header:
            The fits header of the raw frame.
        :init basename:
            The basename for the filename input parameter.
        :init N:
            The number of rows (y-dir)
        :init D:
            The number of cols (x-dir) minus the overscan region
        :init overscan_value:
            Defaults to none but is evaluated as the biweight_location
            of the values in the overscan region
        :init gain:
            (e-/ADU) read from the header
        :init rdnoise:
            (e-) read from the header
        :init amp:
            The amplifier name you are looking at, e.g., "RU" or "LL"
        :init trimsec:
            The CCD section defining the DATASEC.
        :init biassec:
            The CCD section defining the BIASSEC. (overscan region)
        :init fibers:
            Initially an empty list to be filled with Fiber Class Objects,
            one for each fiber in the amplifier.
        :init image:
            The trimmed image that will be manipulated and cleaned during the
            reduction process.
        :init type:
            Observation type.
        :init specid:
            The spectrograph ID for this amplifier.
        :init ifuid:
            The IFU ID for the fiber bundle.
        :init ifuslot:
            The IFU slot position in the Fplane array.
        '''
        # Organization options
        if not op.exists(filename):
            #TODO log warning message
            print("File Does Not Exist: %s" %filename)
            sys.exit(1)
        F = fits.open(filename)
        self.header = F[0].header
        self.name = name
        self.filename = op.abspath(filename)
        self.basename = op.basename(filename)[:-5]
        self.virusconfig = virusconfig
        self.path = path
        if not op.exists(self.path):
            mkpath(self.path)
        self.refit = refit
        self.calpath = calpath
        self.skypath = skypath
        self.darkpath = darkpath
        self.biaspath = biaspath
        self.specname = specname
        self.debug = debug
        
        # Image manipulation options
        self.dark_mult = dark_mult
        self.bias_mult = bias_mult
        self.use_pixelflat = use_pixelflat
        
        # Trace options
        self.fdist = fdist
        self.check_trace = check_trace
        self.trace_poly_order = trace_poly_order
        self.calculate_shift = calculate_shift
        self.col_frac = col_frac
        self.use_trace_ref = use_trace_ref
        self.fdist_ref = fdist_ref
        self.fiber_date = fiber_date
        
        # Fibermodel options
        self.fibmodel_poly_order = fibmodel_poly_order
        self.use_default_fibmodel = use_default_fibmodel
        self.fibmodel_nbins = fibmodel_nbins
        self.make_fib_ind_plots = make_fib_ind_plots
        self.check_fibermodel = check_fibermodel
        self.fsize = fsize
        self.sigma = sigma
        self.power = power
        self.fiber_group = fiber_group
        self.col_group = col_group
        
        # Masking options (Fiberextract related)
        self.mask = mask
        
        # Wavelength Solution options
        self.wave_nbins = wave_nbins
        self.wave_order = wave_order
        self.default_fib = default_fib
        self.init_lims = init_lims
        self.interactive = interactive
        self.check_wave = check_wave        
        self.wave_res = wave_res        
        
        # Smoothing options for individual and master spectra
        self.filt_size_ind = filt_size_ind
        self.filt_size_agg = filt_size_agg
        self.filt_size_final = filt_size_final
        self.filt_size_sky = filt_size_sky
        
        # Continuum subtraction
        self.cont_smooth = cont_smooth
        
        # Image Options
        self.make_residual = make_residual
        self.do_cont_sub = do_cont_sub
        self.make_skyframe = make_skyframe
        
        # Initialized variables
        self.N, self.D = F[0].data.shape
        if self.D == 1064:
            self.D -= 32
        if self.D == 2128:
            self.D -= 64
        if self.N == 1074:
            self.N -= 50
            self.D -= 45
        self.trimmed = False
        self.overscan_value = None
        self.gain = F[0].header['GAIN']
        self.rdnoise = F[0].header['RDNOISE']
        self.amp = (F[0].header['CCDPOS'].replace(' ', '') 
                    + F[0].header['CCDHALF'].replace(' ', ''))
        trim = re.split('[\[ \] \: \,]', F[0].header['TRIMSEC'])[1:-1]
        self.trimsec = [int(t)-((i+1)%2) for i,t in enumerate(trim)]        
        bias = re.split('[\[ \] \: \,]', F[0].header['BIASSEC'])[1:-1]
        self.biassec = [int(t)-((i+1)%2) for i,t in enumerate(bias)]        
        self.fibers = []
        self.type = F[0].header['IMAGETYP'].replace(' ', '')
        self.specid = '%03d' %F[0].header['SPECID']
        self.ifuid = F[0].header['IFUID'].replace(' ', '')
        self.ifuslot ='%03d' %F[0].header['IFUSLOT']
        datetemp = re.split('-',F[0].header['DATE-OBS'])
        self.date = datetime(int(datetemp[0]), int(datetemp[1]), 
                             int(datetemp[2]))
        self.image = np.array(F[0].data, dtype=float)
        self.image_prepped = False
        if self.gain>0:
            self.error = self.rdnoise / self.gain * np.ones((self.N,self.D), 
                                                            dtype=float)
        else:
            self.error = np.zeros((self.N, self.D), dtype=float)
        self.exptime = F[0].header['EXPTIME']
   
    def save(self):
        '''
        Save the entire amplifier include the list of fibers.  
        This property is not used often as "amp*.pkl" is large and typically
        the fibers can be loaded and the other amplifier properties quickly
        recalculated.
        '''
        fn = op.join(self.path, 'amp_%s.pkl' % self.basename)
        if not op.exists(self.path):
            os.mkdir(self.path)
        with open(fn, 'wb') as f:
           pickle.dump(self, f)
           

    def load_fibers(self):
        '''
        Load fibers in self.path. Redefine the path for the fiber to self.path
        in case it was copied over. After loaded, evaluate the fibermodel as 
        well as the wavelength solution if available.  
        '''
        if not self.fibers:
            fn = op.join(self.path, 'fiber_*_%s_%s_%s_%s.pkl' %(self.specid, 
                                                                self.ifuslot,
                                                                self.ifuid,
                                                                self.amp))
            files = sorted(glob.glob(fn))
            for fiber_fn in files:
                if op.exists(fiber_fn):
                    with open(fiber_fn, 'r') as f:
                        self.fibers.append(pickle.load(f))
                        self.fibers[-1].eval_fibmodel_poly()
                        self.fibers[-1].path = self.path
                        if self.fibers[-1].wave_polyvals is not None:
                            self.fibers[-1].eval_wave_poly()
            
            self.good_fibers = [fiber for fiber in self.fibers 
                                      if not fiber.dead]
            self.dead_fibers = [fiber for fiber in self.fibers 
                                      if fiber.dead] 

    def convert_binning(self, fiber, prop):
        '''
        Occassionally the binning of property being loaded from calibration
        or otherwise is not binned the same as the data.  This function 
        converts between different binning if necessary.  The properties
        affected by this are "fibmodel_x", "trace", and "fiber_to_fiber".  
        Others are immune due to their evaluation methods.
        :param fiber:
            A fiber class object from which you are loading "prop".
        :param prop:
            A property to load from "fiber".
        '''
        if prop == 'fibmodel_x':
            values = getattr(fiber, prop)
            return (1.* values) / fiber.D * self.D
        elif prop in ['trace', 'fiber_to_fiber']:
            values = getattr(fiber, prop)
            return np.interp((1.*np.arange(self.D))/self.D, 
                             (1.*np.arange(fiber.D))/fiber.D, values)
            
        else:
            try:
                return 1.* getattr(fiber, prop)
            except TypeError:
                print(fiber.fibnum-1,prop, getattr(fiber,prop))
                sys.exit()
                             
                             
    def load_cal_property(self, prop, pathkind='calpath'):
        '''
        Load a specific property from a calibration object.  This can be
        "trace" from a twighlight frame or "sky_spectrum" from another
        science frame.  
        :param prop:
            A property to load from a set of fibers.
        :param pathkind:
            Used to defined the path from the larger class.  E.g., "calpath"
            or "skypath".
        '''
        path = getattr(self, pathkind)
        fn = op.join(path,'fiber_*_%s_%s_%s_%s.pkl' %(self.specid, 
                                                                  self.ifuslot,
                                                                  self.ifuid,
                                                                  self.amp))
        if isinstance(prop, basestring):
            prop = [prop]
        files = sorted(glob.glob(fn))
        for i, fiber_fn in enumerate(files):
            fcheck = op.join(path,'fiber_%03d_%s_%s_%s_%s.pkl' %(i+1, 
                                                                  self.specid, 
                                                                  self.ifuslot,
                                                                  self.ifuid,
                                                                  self.amp))
            if fcheck != fiber_fn:
                print("Mismatch in loading fiber files from cal directory.")
                print("The %i fiber did not match %s" %(i,fiber_fn))
                sys.exit(1)
            append_flag = False
            try:
                F = self.fibers[i]
            except IndexError:    
                F = Fiber(self.D, i+1, self.path, self.filename)
                append_flag = True
            with open(fiber_fn, 'r') as f:
                F1 = pickle.load(f)
            for pro in prop:
                if getattr(F1,pro) is None:
                    setattr(F, pro, getattr(F1,pro))
                else:
                    try:
                        setattr(F, pro, self.convert_binning(F1,pro))
                    except AttributeError:
                        if self.debug:
                            print("Cannot load attribute %s from %s" %(pro, 
                                                                     fiber_fn))
            if append_flag:
                self.fibers.append(F)
    
    
    def load_all_cal(self):
        '''
        Load all calibration properties to current fiber set and evaluate
        the fibermodel and wavelength solution.
        '''
        self.load_cal_property(['trace','fibmodel_polyvals',
                                'fibmodel_x','fibmodel_y','binx',
                                'wave_polyvals','fiber_to_fiber',
                                'dead'])
        self.good_fibers = [fiber for fiber in self.fibers 
                                      if not fiber.dead]
        self.dead_fibers = [fiber for fiber in self.fibers 
                                      if fiber.dead] 
        for fiber in self.fibers:
            fiber.eval_fibmodel_poly()
            fiber.eval_wave_poly()
      

    def save_fibers(self):
        '''
        Save the fibers to self.path using the fiber class "save" function.
        '''
        for fiber in self.fibers:
            fiber.save(self.specid, self.ifuslot, self.ifuid, self.amp)
            
      
    def orient_image(self):
        '''
        Orient the images from blue to red (left to right)
        Fibers are oriented to match configuration files
        '''
        if self.amp == "LU":
            self.image[:] = self.image[::-1,::-1]
            self.error[:] = self.error[::-1,::-1]
        if self.amp == "RL":
            self.image[:] = self.image[::-1,::-1]
            self.error[:] = self.error[::-1,::-1]

            
        
    def subtract_overscan(self):
        '''
        Evaluate the overscan_value using a biweight average of the BIASSEC
        region.  Only calculate the value if one does not exist or 
        recalculate is set to True.
        '''
        if self.overscan_value is None:
            self.overscan_value = biweight_location(self.image[
                                              self.biassec[2]:self.biassec[3],
                                              self.biassec[0]:self.biassec[1]])
            self.image[:] -= self.overscan_value


    def trim_image(self):
        '''
        Trim the image to just the datasec/trimsec.
        '''
        if not self.trimmed:
            self.image = self.image[self.trimsec[2]:self.trimsec[3], 
                                       self.trimsec[0]:self.trimsec[1]]
            self.trimmed = True
      
      
    def subtract_dark(self):
        if self.dark_mult>0.0:
            darkimage = np.array(fits.open(op.join(self.darkpath, 
                                                'masterdark_%s_%s.fits' 
                                            %(self.specid, self.amp)))[0].data, 
                              dtype=float)
            self.image[:] = self.image - self.dark_mult * darkimage
            #self.error[:] = np.sqrt(self.error**2 + self.gain*self.dark_mult*darkimage)
            
            
    def subtract_bias(self):
        if self.bias_mult>0.0:
            biasimage = np.array(fits.open(op.join(self.biaspath, 
                                                'masterbias_%s_%s.fits' 
                                            %(self.specid, self.amp)))[0].data, 
                              dtype=float)
            self.image[:] = self.image - self.bias_mult * biasimage
            #self.error[:] = np.sqrt(self.error**2 + self.gain*self.bias_mult*biasimage)
            
            
    def multiply_gain(self):
        self.image *= self.gain
        self.error *= self.gain
        
        
    def calculate_photonnoise(self):
        self.error[:] = np.sqrt(self.error**2 + self.image)
        
        
    def divide_pixelflat(self):
        if self.use_pixelflat:
            pixelflat = np.array(fits.open(op.join(self.virusconfig, 
                                                   'PixelFlats','20161223',
                                                   'pixelflat_cam%s_%s.fits' 
                                            %(self.specid, self.amp)))[0].data,
                                  dtype=float)
            self.image[:] = np.where(pixelflat != 0, self.image / pixelflat, 
                                     0.0)
            self.error[:] = np.where(pixelflat != 0, self.error / pixelflat, 
                                     0.0)
             
                                     
                                     
    def prepare_image(self):
        '''
        This many purpose function loads the image, finds the overscan value,
        subtracts the dark image and bias image, multplies the gain, 
        and divides the pixelflat.  It also orients the image using the
        "orient" function above.
        '''
        self.subtract_overscan()
        self.trim_image()
        self.multiply_gain()
        self.calculate_photonnoise()
        self.subtract_bias()
        self.subtract_dark()
        self.divide_pixelflat()
        self.orient_image()
        self.image_prepped = True
        
    
    def find_shift(self):
        '''
        Find the shift in the trace compared to the calibration fibers in
        self.calpath.  If they are the same then the shift will be 0.  
        This has not been tested yet.
        '''
        fn = op.join(self.calpath,'fiber_*_%s_%s_%s_%s.pkl' %(self.specid, 
                                                                  self.ifuslot,
                                                                  self.ifuid,
                                                                  self.amp))
        files = sorted(glob.glob(fn))
        shift = []
        for i, fiber_fn in enumerate(files):
            fcheck = op.join(self.calpath,'fiber_%03d_%s_%s_%s_%s.pkl' %(i+1, 
                                                                  self.specid, 
                                                                  self.ifuslot,
                                                                  self.ifuid,
                                                                  self.amp))
            if fcheck != fiber_fn:
                print("Mismatch in loading fiber files from cal directory.")
                print("The %i fiber did not match %s" %(i,fiber_fn))
                sys.exit(1)
            try:
                F = self.fibers[i]
            except IndexError:    
                print("No trace measured yet, so no shift measured")
                return None
            with open(fiber_fn, 'r') as f:
                F1 = pickle.load(f)
            col = 4.*self.D/5.
            width = 20
            low = int(col-width)
            high = int(col+width+1)
            shift.append(biweight_location(F.trace[low:high] 
                              - F1.trace[low:high]))
        self.shift = shift
        return biweight_location(np.array(shift))


    def get_attribute_from_neighbor_fiber(self, ind1, ind2, prop):
        '''
        This small function is used to get an attribute from the fiber below
        it.
        '''
        if isinstance(prop, basestring):
            prop = [prop]
        for i, pro in enumerate(prop):
            setattr(self.fibers[ind1], pro, 1.*getattr(self.fibers[ind2], pro))

    
    def fill_in_dead_fibers(self, props, return_ind=False):
        '''
        This function fills in dead fibers by looking at neighbors which are
        not dead and filling in their info.
        '''
        if return_ind:
            keep_ind=[]
        for fiber in self.dead_fibers:
            i = fiber.fibnum - 1
            j = 1
            no_neighbor = True
            while no_neighbor:
                if i-j >=0:
                    if not self.fibers[i-j].dead:
                        self.get_attribute_from_neighbor_fiber(i, i-j, props)
                        no_neighbor=False
                        if return_ind:
                            keep_ind.append(i-j)
                if i+j<len(self.fibers) and no_neighbor:
                    if not self.fibers[i+j].dead:
                        self.get_attribute_from_neighbor_fiber(i, i+j, props)
                        no_neighbor=False
                        if return_ind:
                            keep_ind.append(i+j)
                j+=1
                if i-j<0 and ((i+j)>=len(self.fibers)):
                    print(i,j,len(self.dead_fibers))
                    sys.exit(1)
        if return_ind:
            return keep_ind
            


    def get_trace(self):
        '''
        This function gets the trace for this amplifier.  It checks functional
        dependencies first: prepare_image().  If self.type is 'twi' or self.refit 
        is True then the trace is calculated, otherwise the trace is loaded 
        from calpath.
        '''                      
          
        if not self.image_prepped:
            self.prepare_image()
        if self.type == 'twi' or self.refit:
            if self.refit:
                mx_cut=0.1
            else:
                mx_cut=0.1
            allfibers, xc = get_trace_from_image(self.image, interp_window=2.5,
                                                 debug=False, mx_cut=mx_cut)
            brcol = np.argmin(np.abs(xc-self.D*self.col_frac))
            if self.use_trace_ref:
                if self.fiber_date is None:
                    fn = glob.glob(op.join(self.virusconfig, 
                                           'Fiber_Locations','*')+'/')
                    dates = [op.basename(op.dirname(f)) for f in fn]
                    timediff = np.zeros((len(dates),))
                    for i,date in enumerate(dates):
                        d = datetime(int(date[:4]), int(date[4:6]),
                                     int(date[6:]))
                        timediff[i] = np.abs((self.date - d).days)
                    closest_date = dates[np.argmin(timediff)]
                    ref_file = np.loadtxt(op.join(self.virusconfig, 
                                                  'Fiber_Locations',
                                                  closest_date, 
                                                  'fiber_loc_%s_%s_%s_%s.txt'
                                                  %(self.specid, self.ifuslot, 
                                                    self.ifuid, self.amp)))
                else:    
                    ref_file = np.loadtxt(op.join(self.virusconfig, 
                                                  'Fiber_Locations',
                                                  self.fiber_date, 
                                                  'fiber_loc_%s_%s_%s_%s.txt'
                                                  %(self.specid, self.ifuslot, 
                                                    self.ifuid, self.amp)))
                # sort by y values just in case the missing fiber is at the end
                ref_file = ref_file[ref_file[:,0].argsort(),:]
                standardcol=ref_file[:,0]
            else:
                standardcol = allfibers[brcol]
            cols1 = xc[brcol::-1]
            cols2 = xc[(brcol+1)::1]
            # Initialize fiber traces
            for i in xrange(len(standardcol)):
                try: 
                    F = self.fibers[i]
                except IndexError:    
                    F = Fiber(self.D, i+1, self.path, self.filename)
                    self.fibers.append(F)
                self.fibers[i].trace_poly_order = self.trace_poly_order
                self.fibers[i].init_trace_info()
                fdist = standardcol[i]-allfibers[brcol]
                floc = np.argmin(np.abs(fdist))
                if np.abs(fdist[floc])<self.fdist_ref:    
                    self.fibers[i].trace_x[brcol] = brcol
                    self.fibers[i].trace_y[brcol] = allfibers[brcol][floc]
                else:
                    self.fibers[i].dead=True
            self.good_fibers = [fiber for fiber in self.fibers 
                                      if not fiber.dead]
            self.dead_fibers = [fiber for fiber in self.fibers 
                                      if fiber.dead]    
            for c in cols1:
                loc = np.where(xc==c)[0]
                for i,fiber in enumerate(self.good_fibers):
                    yvals = allfibers[int(loc)]
                    if not yvals.size:
                        continue
                    xloc = np.argmin(np.abs(fiber.trace_x - c))
                    floc = np.argmin(np.abs(fiber.trace_y[xloc] 
                                            - yvals))
                    if (np.abs(fiber.trace_y[xloc]-yvals[floc]) < self.fdist):
                        fiber.trace_x[c] = c
                        fiber.trace_y[c] = yvals[floc]
            for c in cols2:
                loc = np.where(xc==c)[0]
                for i,fiber in enumerate(self.good_fibers):
                    yvals = allfibers[int(loc)]
                    if not yvals.size:
                        continue
                    xloc = np.argmin(np.abs(fiber.trace_x - c))
                    floc = np.argmin(np.abs(fiber.trace_y[xloc] 
                                            - yvals))
                    if (np.abs(fiber.trace_y[xloc]-yvals[floc]) < self.fdist):
                        fiber.trace_x[c] = c
                        fiber.trace_y[c] = yvals[floc]
            # Evaluate good fibers with trace defined everywhere measured
            for fib, fiber in enumerate(self.good_fibers):
                if np.sum(fiber.trace_x != fiber.flag)==len(xc):
                    fiber.fit_trace_poly()
                    fiber.eval_trace_poly()
            # Fill in the blank for fibers with trace flagged
            for fib, fiber in enumerate(self.good_fibers):
                if np.sum(fiber.trace_x != fiber.flag)!=len(xc):
                    sel = np.where(fiber.trace_x != fiber.flag)[0]
                    setdiff = np.setdiff1d(xc, sel)
                    try:
                        fiber.fit_trace_poly()
                    except TypeError:
                        print(fib)
                        sys.exit(1)
                    k=1
                    done=False
                    if (fib+k)<=(len(self.good_fibers)-1):
                        if np.all(self.good_fibers[fib+k].trace > 0):
                            dif = np.interp(setdiff, fiber.trace_x[sel], 
                                            fiber.trace_y[sel] - 
                                            self.fibers[fib+k].trace[sel])
                            fiber.trace_x[setdiff] = setdiff
                            fiber.trace_y[setdiff] = (dif + 
                                        self.good_fibers[fib+k].trace[setdiff])
                            fiber.eval_trace_poly()
                            done=True
                    if (fib-k) >= 0 and not done:
                        if np.all(self.good_fibers[fib-k].trace > 0):
                            dif = np.interp(setdiff, fiber.trace_x[sel], 
                                            fiber.trace_y[sel] - 
                                            self.good_fibers[fib-k].trace[sel])
                            fiber.trace_x[setdiff] = setdiff
                            fiber.trace_y[setdiff] = (dif + 
                                        self.good_fibers[fib-k].trace[setdiff])
                            fiber.eval_trace_poly()
                            done=True
                    if not done:
                        fiber.trace_x[setdiff] = setdiff
                        fiber.trace_y[setdiff] = np.polyval(
                                                          fiber.trace_polyvals, 
                                                              setdiff / self.D)
                        fiber.eval_trace_poly()
            ind = self.fill_in_dead_fibers(['trace_x', 'trace_y', 'trace'], 
                                           return_ind=True)
            for i, fiber in enumerate(self.dead_fibers):
                fiber.trace_y += (standardcol[fiber.fibnum-1]
                                  -standardcol[ind[i]])
                fiber.trace += (standardcol[fiber.fibnum-1]
                                -standardcol[ind[i]])
                
            # TODO print trace info
            fn = op.join(self.path, self.basename + '_trace.txt')
            A = np.zeros((len(self.fibers),4))
            A[:,0] = [fiber.fibnum for fiber in self.fibers]
            A[:,1] = [fiber.trace[int(self.D/6.)] for fiber in self.fibers]
            A[:,2] = [fiber.trace[int(self.D/2.)] for fiber in self.fibers]
            A[:,3] = [fiber.trace[int(5.*self.D/6.)] for fiber in self.fibers]
            np.savetxt(fn, A)
            if self.calculate_shift:
                self.net_trace_shift = self.find_shift()
                smooth_shift = biweight_filter(self.shift, 25)
                if self.net_trace_shift is not None:
                    self.load_cal_property('trace')
                    for i, fiber in enumerate(self.fibers):
                        fiber.trace[:] = fiber.trace + smooth_shift[i]
        else:
            self.load_cal_property(['trace','dead'])
            self.good_fibers = [fiber for fiber in self.fibers 
                                      if not fiber.dead]
            self.dead_fibers = [fiber for fiber in self.fibers 
                                      if fiber.dead]  
            for fiber in self.fibers:
                fiber.eval_trace_poly()       

        
        if self.check_trace:
            outfile = op.join(self.path,'trace_%s.png' %self.basename)
            check_fiber_trace(self.image, self.fibers, outfile)
            
                
    def get_fibermodel(self):
        '''
        This function gets the fibermodel for this amplifier.  It checks 
        functional dependencies first: prepare_image() and get_trace().  
        If self.type is 'twi' or self.refit is True then the fibermodel is 
        calculated, otherwise the fibermodel is loaded and evaluated
        from calpath.
        
        The fiber model is currently a linear interpolation between amplitudes
        of different bins over the fiber size.  Critically, "bins", "fsize",
        "sigma", and "power" set the initial x-values for each bin where x
        is the distance in pixels from the fiber trace.
        
        The fiber model is fit using image stamps containing a number of 
        fibers, "fiber_group", surrounding the target fiber 
        and number of columns, "col_group".  Over this
        stamp, a single fiber model is fit to all relevant fibers.  This is
        done for each fiber in a moving window sense, but done only once in
        the column direction in an gridded sense.
        
        '''
        if not self.image_prepped:
            self.prepare_image()
        if not self.fibers:
            self.get_trace()
        if self.type == 'twi' or self.refit:
            sol, xcol, binx = fit_fibermodel_nonparametric(self.image, 
                                                              self.good_fibers,
                                                                   debug=False,
                                         use_default=self.use_default_fibmodel,
                                                  plot=self.make_fib_ind_plots,
                                                           outfolder=self.path,
                                                  fiber_group=self.fiber_group,
                                                      col_group=self.col_group,
                                                      bins=self.fibmodel_nbins,
                                                              fsize=self.fsize,
                                                              sigma=self.sigma,
                                                              power=self.power)
            nfibs, ncols, nbins = sol.shape
            for i, fiber in enumerate(self.good_fibers):
                fiber.fibmodel_poly_order = self.fibmodel_poly_order
                fiber.fibmodel_x = xcol
                fiber.fibmodel_y = sol[i,:,:]
                fiber.binx = binx
                fiber.fit_fibmodel_poly()
                fiber.eval_fibmodel_poly()
            self.fill_in_dead_fibers(['fibmodel_poly_order', 'fibmodel_x', 
                                      'fibmodel_y', 'binx', 'fibmodel'])
                        
        else:
            self.load_cal_property(['fibmodel_polyvals','binx'])
            for fiber in self.fibers:
                fiber.eval_fibmodel_poly()
                
        if self.check_fibermodel:
            if self.fibers[0].spectrum is None:
                norm = get_norm_nonparametric_fast(self.image, self.fibers,
                                                   mask=self.mask)
                for i, fiber in enumerate(self.fibers):
                    fiber.spectrum = norm[i,:]
            outfile = op.join(self.path,'fibmodel_%s.png' %self.basename)
            check_fiber_profile(self.image, self.fibers, outfile)


    def fiberextract(self, cols=None):
        '''
        This function gets the spectrum for each fiber.  It checks 
        functional dependencies first: prepare_image(), get_trace(), and
        get_fibermodel(). 

        '''
        if not self.image_prepped:
            self.prepare_image()
        if not self.fibers:
            self.get_trace()
        if self.fibers[0].fibmodel is None:
            self.get_fibermodel()
        else:
            for fiber in self.fibers:
                fiber.eval_fibmodel_poly()
        
        norm = get_norm_nonparametric_fast(self.image, self.fibers, 
                                           cols=cols, mask=self.mask)
                                           
        for i, fiber in enumerate(self.fibers):
            fiber.spectrum = norm[i,:]    
    
    def get_wavelength_solution(self):
        '''
        This function gets the wavelength solution for each fiber.  It checks 
        functional dependencies first: prepare_image(), get_trace(),
        get_fibermodel(), and fiberextract().
        
        The wavelength solution is done for an initial fiber first.  In bins
        a linear solution is fit using a chi^2 minimization comparing a
        default solar/twi spectrum compared to this amplifiers twi spectrum.
        Both are normalized before chi^2 minimization.  A polynomial is then
        fit to the collection of linear solutions.  After the first fiber
        neighboring fibers start with previous solution as starting points
        for the binned linear fits.

        '''                                    
        solar_spec = np.loadtxt(op.join(self.virusconfig,
                                        'solar_spec/%s_temp.txt' 
                                        %self.specname))
        if not self.image_prepped:
            self.prepare_image()
        if not self.fibers:
            self.get_trace()
        if self.fibers[0].fibmodel is None:
            self.get_fibermodel()
        else:
            for fiber in self.fibers:
                fiber.eval_fibmodel_poly() 
        if self.type == 'twi' or self.refit:
            if self.fibers[0].spectrum is None:
                norm = get_norm_nonparametric_fast(self.image, self.fibers, 
                                                   mask=self.mask)
                for i, fiber in enumerate(self.fibers):
                    fiber.spectrum = norm[i,:]
            if self.init_lims is None:
                print("Please provide initial wavelength endpoint guess")
                sys.exit(1)
            for k in xrange(2):
                content=False
                cnting = 0
                while content==False:
                    fiber = self.good_fibers[self.default_fib]
                    fw, fwp = calculate_wavelength_chi2(np.arange(self.D), 
                                                        solar_spec,
                                                        self.good_fibers,
                                                        self.default_fib,
                                                        self.fiber_group,
                                                      init_lims=self.init_lims, 
                                                        debug=False, 
                                                  interactive=self.interactive,
                                                        nbins=self.wave_nbins,
                                                        res=self.wave_res)
                    fiber.wavelength = fw*1.
                    fiber.wave_polyvals = fwp*1.
                    # Boundary check:
                    if (np.abs(fiber.wavelength.min()-self.init_lims[0])>100. 
                     or np.abs(fiber.wavelength.max()-self.init_lims[1])>100.):
                        self.default_fib = np.random.choice(112) 
                        cnting+=1
                    else:
                        content=True
                    if cnting>9:
                        print("Ran through 9 loops but no solution found.")
                        sys.exit(1)
                fc = np.arange(len(self.good_fibers))
                if self.default_fib==0:
                    fibs1 = []
                else:
                    fibs1 = fc[(self.default_fib-1)::-1]
                if self.default_fib==(len(self.good_fibers)-1):
                    fibs2 = []
                else:
                    fibs2 = fc[(self.default_fib+1)::1]
                for fibn in fibs1:
                    fiber = self.good_fibers[fibn]
                    fw, fwp = calculate_wavelength_chi2(np.arange(self.D), 
                                                        solar_spec,
                                                        self.good_fibers,
                                                        fibn,
                                                        self.fiber_group,
                                                      init_lims=self.init_lims, 
                                                        debug=False, 
                                                       interactive=False,
                                     init_sol=self.fibers[fibn+1].wave_polyvals,
                                                        nbins=self.wave_nbins,
                                                        res=self.wave_res)
                    fiber.wavelength = fw*1.
                    fiber.wave_polyvals = fwp*1.
                for fibn in fibs2:
                    fiber = self.good_fibers[fibn]
                    fw, fwp = calculate_wavelength_chi2(np.arange(self.D), 
                                                        solar_spec,
                                                        self.good_fibers,
                                                        fibn,
                                                        self.fiber_group,
                                                      init_lims=self.init_lims, 
                                                        debug=False, 
                                                       interactive=False,
                                     init_sol=self.fibers[fibn-1].wave_polyvals,
                                                        nbins=self.wave_nbins,
                                                        res=self.wave_res)
                    fiber.wavelength = fw*1.
                    fiber.wave_polyvals = fwp*1.
                if k==0:
                    self.get_master_sky(norm=True)
                    solar_spec = np.zeros((len(self.masterwave),2))
                    solar_spec[:,0] = self.masterwave
                    solar_spec[:,1] = self.mastersmooth
            self.fill_in_dead_fibers(['wavelength', 'wave_polyvals'])        

        else:
            self.load_cal_property(['wave_polyvals'])
            for fiber in self.fibers:
                fiber.eval_wave_poly()
        if self.check_wave:
            if self.fibers[0].spectrum is None:
                norm = get_norm_nonparametric_fast(self.image, self.fibers, 
                                                   mask=self.mask)
                for i, fiber in enumerate(self.fibers):
                    fiber.spectrum = norm[i,:]
            outfile = op.join(self.path,'wavesolution_%s.png' %self.basename)
            check_wavelength_fit(self.fibers, solar_spec, outfile)
                
                    
    def get_fiber_to_fiber(self):
        '''
        This function gets the fiber to fiber normalization for this amplifier. 
        It checks functional dependencies first: prepare_image(), get_trace(), 
        get_fibermodel(), fiberextract(), and get_wavelength_solution().
        '''
        if not self.image_prepped:
            if self.debug:
                print("Building image for %s" %self.basename)
            self.prepare_image()
        if not self.fibers:
            if self.debug:
                print("Getting trace for %s" %self.basename)
            self.get_trace()
        if self.fibers[0].fibmodel is None:
            if self.debug:
                print("Getting fibermodel for %s" %self.basename)
            self.get_fibermodel()
        else:
            for fiber in self.fibers:
                fiber.eval_fibmodel_poly()
        if self.type == 'twi' or self.refit:
            if self.fibers[0].spectrum is None:
                if self.debug:
                    print("Fiberextracting %s" %self.basename)
                self.fiberextract()
            if self.fibers[0].wave_polyvals is None:
                if self.debug:
                    print("Getting Wavelength solution for %s" %self.basename)
                self.get_wavelength_solution()
            else:
                for fiber in self.fibers:
                    fiber.eval_wave_poly()
            if self.debug:
                print("Getting Fiber to Fiber for %s" %self.basename)
            masterwave = []
            masterspec = []
            for fib, fiber in enumerate(self.good_fibers):
                masterwave.append(fiber.wavelength)
                masterspec.append(fiber.spectrum)
            masterwave = np.hstack(masterwave)
            smoothspec = np.hstack(masterspec)
            ind = np.argsort(masterwave)
            masterwave[:] = masterwave[ind]
            smoothspec[:] = smoothspec[ind]
            self.averagespec = biweight_filter(smoothspec, self.filt_size_agg)
            for fib, fiber in enumerate(self.fibers):
                fiber.fiber_to_fiber = biweight_filter(fiber.spectrum 
                                      / np.interp(fiber.wavelength, masterwave, 
                                                  self.averagespec), 
                                                       self.filt_size_final)

        else:
            self.load_cal_property(['fiber_to_fiber'])   
            
        
    def sky_subtraction(self, cols=None):
        '''
        This function gets the master sky spectrum and 
        evaluates the sky_spectrum for each fiber. It then builds a sky image
        and a sky-subtracted image.  It checks functional dependencies first: 
        prepare_image(), get_trace(), get_fibermodel(), fiberextract(), 
        get_wavelength_solution(), and fiber_to_fiber().        
        '''
        if not self.image_prepped:
            self.prepare_image()
        if not self.fibers:
            self.get_trace()
        if self.fibers[0].fibmodel is None:
            self.get_fibermodel()
        else:
            for fiber in self.fibers:
                fiber.eval_fibmodel_poly()
        if self.fibers[0].fiber_to_fiber is None:
            self.load_cal_property(['fiber_to_fiber'])
        if self.fibers[0].spectrum is None:
            self.fiberextract()
        if self.fibers[0].wave_polyvals is None:
            self.get_wavelength_solution()
        else:
            for fiber in self.fibers:
                fiber.eval_wave_poly()
        if self.fibers[0].fiber_to_fiber is None:
            self.get_fiber_to_fiber()
        if self.skypath is not None:
            self.load_cal_property('sky_spectrum', pathkind='skypath')
            if self.fibers[0].sky_spectrum is None:
                print("Loading sky spectrum from %s did not work." 
                      %self.skypath)
                print("Setting skypath to None for this amplifier.")
                self.skypath = None
        if self.skypath is None:
            self.get_master_sky(sky=True)
            for fib, fiber in enumerate(self.fibers):
                fiber.sky_spectrum = (fiber.fiber_to_fiber 
                                 * np.interp(fiber.wavelength, self.masterwave, 
                                             self.mastersky))
        if self.make_skyframe: 
            self.skyframe = get_model_image(self.image, self.fibers, 
                                            'sky_spectrum', debug=False)
            self.clean_image = self.image - self.skyframe
        if self.do_cont_sub:
            for fib, fiber in enumerate(self.fibers):
                fiber.continuum = biweight_filter(fiber.spectrum 
                                                  -fiber.sky_spectrum, 
                                                  self.cont_smooth, 
                                                  ignore_central=7)
            self.cont_frame = get_model_image(self.image, self.fibers, 
                                            'continuum', debug=False)
            self.continuum_sub = self.image - self.skyframe - self.cont_frame
        if self.make_residual:
            self.model = get_model_image(self.image, self.fibers, 'spectrum', 
                                         debug=False)
            self.residual = self.image - self.model
        
        
    def clean_cosmics(self):
        '''
        We use a direct copy of Malte Tewes and Pieter Van Dokkum's cosmics.py
        which is a python-interface of the LA cosmics algorithm to remove
        cosmics from sky-subtracted frames.
        
        '''
        cc = cosmics.cosmicsimage(self.clean_image, gain=1.0, 
                                  readnoise=self.rdnoise, 
                                  sigclip=25.0, sigfrac=0.001, objlim=0.001,
                                  satlevel=-1.0)
        cc.run(maxiter=1)
        c = np.where(cc.mask == True)
        self.mask = np.zeros(self.image.shape)
        for x, y in zip(c[0], c[1]):
            self.mask[x][y] = -1.0 
             
             
    def get_master_sky(self, sky=False, norm=False):
        '''
        This builds a master sky spectrum from the spectra of all fibers
        using a biweight average of a wavelength ordered master array.
        
        '''
        masterwave = []
        if sky:
            masterspec = []
        if norm:
            mastersmooth=[]
        for fib, fiber in enumerate(self.good_fibers):
            if norm:
                y = biweight_filter(fiber.spectrum, self.filt_size_ind)
                mastersmooth.append(y/fiber.spectrum)
            masterwave.append(fiber.wavelength)
            if sky:            
                masterspec.append(fiber.spectrum/fiber.fiber_to_fiber)
        masterwave = np.hstack(masterwave)
        ind = np.argsort(masterwave)
        masterwave[:] = masterwave[ind]
        self.masterwave = masterwave
        if sky:
            masterspec = np.hstack(masterspec)
            masterspec[:] = masterspec[ind]
            self.mastersky = biweight_filter(masterspec, self.filt_size_sky)
        if norm:
            mastersmooth = np.hstack(mastersmooth)
            mastersmooth[:] = mastersmooth[ind]
            self.mastersmooth = biweight_filter(mastersmooth, 
                                                self.filt_size_sky)     