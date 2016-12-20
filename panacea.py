#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IFU Reduction Code 
------------------
Built for the VIRUS instrument as well as LRS2 on HET

Incomplete Documentation



"""

from __future__ import (division, print_function, absolute_import,
                        unicode_literals)
                        
import matplotlib
matplotlib.use('agg')
import time

import numpy as np
import os.path as op
from astropy.io import fits
from pyhetdex.cure.distortion import Distortion

from args import parse_args
from amplifier import Amplifier
from fiber_utils import get_model_image
from utils import matrixCheby2D_7, biweight_filter, biweight_midvariance
import config

                      
                      
def recreate_fiberextract(instr1, instr2, wavelim, disp):
    col = int(instr1.D / 2)
    intv = [1, 1+instr1.D]
    ypos = np.array([fiber.trace+intv[v] for v,instr in enumerate([instr1,instr2]) 
                                   for fiber in instr.fibers])
    allspec = np.array([fiber.spectrum/fiber.fiber_to_fiber 
                                   for v,instr in enumerate([instr1,instr2]) 
                                   for fiber in instr.fibers])                                       
    allskys = np.array([(fiber.spectrum-fiber.sky_spectrum)/fiber.fiber_to_fiber 
                                   for v,instr in enumerate([instr1,instr2]) 
                                   for fiber in instr.fibers])
    allwave = np.array([fiber.wavelength for v,instr in enumerate([instr1,instr2]) 
                                   for fiber in instr.fibers])
    f1 = ypos[:,col]
    order = np.argsort(f1)[::-1]
    orderspec = allspec[order,:]
    orderskys = allskys[order,:]
    orderwave = allwave[order,:]
    wv = np.arange(wavelim[0], wavelim[1]+disp, disp)
    a,b = orderspec.shape
    newspec = np.zeros((a, len(wv)))
    newskys = np.zeros((a, len(wv)))
    for i in xrange(a):
        diff_wave = np.diff(orderwave[i,:])
        wi = orderwave[i,:-1]
        df = np.interp(wv, wi, diff_wave, left=0.0, right=0.0)
        fl = np.interp(wv, wi, orderspec[i,:-1], left=0.0, right=0.0)
        fs = np.interp(wv, wi, orderskys[i,:-1], left=0.0, right=0.0)
        newspec[i,:] = np.where(df!=0, fl/df*disp, 0.0)
        newskys[i,:] = np.where(df!=0, fs/df*disp, 0.0)
    return newspec, newskys
        
    
def recalculate_dist_coeff(D, instr1, instr2):
    col = int(instr1.D / 2)
    intv = [1, 1+instr1.D]
    ypos = np.array([fiber.trace+intv[v] for v,instr in enumerate([instr1,instr2]) 
                                   for fiber in instr.fibers])
    xpos = np.array([np.arange(fiber.D) for instr in [instr1,instr2] 
                                        for fiber in instr.fibers])
    f1 = ypos[:,col]
    f0 = np.sort(f1)[::-1]
    fpos = np.zeros((ypos.shape))
    k=0
    for instr in [instr1,instr2]:
        for fiber in instr.fibers:
            fpos[k,:] = f1[k]
            k+=1
            
    wpos = np.array([fiber.wavelength for instr in [instr1,instr2] 
                                      for fiber in instr.fibers])    
    
    Vxy = matrixCheby2D_7(D._scal_x(xpos.ravel()), 
                             D._scal_y(ypos.ravel()))
    Vwf = matrixCheby2D_7(D._scal_w(wpos.ravel()), 
                             D._scal_f(fpos.ravel()))
    Vxf = matrixCheby2D_7(D._scal_x(xpos.ravel()), 
                             D._scal_f(fpos.ravel())) 
    D.reference_f_.data = f0*1.
    D.fiber_par_.data = np.linalg.lstsq(Vxy, fpos.ravel())[0]
    D.wave_par_.data = np.linalg.lstsq(Vxy, wpos.ravel())[0]
    D.x_par_.data = np.linalg.lstsq(Vwf, xpos.ravel())[0]
    D.y_par_.data = np.linalg.lstsq(Vwf, ypos.ravel())[0]
    D.fy_par_.data = np.linalg.lstsq(Vxf, ypos.ravel())[0]
    D.x_offsets = f0*0.
    D.wave_offsets = f0*0.
    return D
    
def make_cube_file(args, filename, ifucen, scale, side):
    if args.instr.lower() == "lrs2":
        outname = op.join(op.dirname(filename),'Cu' + op.basename(filename))
        print("Making Cube image for %s" %op.basename(outname))
        try:
            F = fits.open(filename)
        except IOError:
            print("Could not open %s" %filename)
            return None
        data = F[0].data
        a,b = data.shape
        x = np.arange(ifucen[:,1].min()-scale, ifucen[:,1].max()+scale, scale)
        y = np.arange(ifucen[:,2].min()-scale, ifucen[:,2].max()+scale, scale)
        xgrid, ygrid = np.meshgrid(x, y)
        zgrid = np.zeros((b,)+xgrid.shape)
        for k in xrange(b):
            for i in xrange(len(x)):
                for j in xrange(len(y)):
                    d = np.sqrt((ifucen[:,1] - xgrid[j,i])**2 + 
                                (ifucen[:,2] - ygrid[j,i])**2)
                    w = np.exp(-1./2.*(d/1.)**2)
                    sel = w > 1e-3
                    zgrid[k,j,i] = np.sum(data[sel,k]*w[sel])/np.sum(w[sel])
        hdu = fits.PrimaryHDU(zgrid)
        hdu.header['CDELT3'] = F[0].header['CDELT1']
        hdu.header['CRVAL3'] = F[0].header['CRVAL1']
        hdu.header['CRPIX3'] = F[0].header['CRPIX1']
        hdu.writeto(outname, clobber=True)
    if args.instr.lower() == "virus":
        if side == "R":
            file2 =filename
            file1 = filename[:-6] + "L.fits"
        else:
            return None
        if not op.exists(file2):
            print("Could not open %s" %file2)
            return None
        if not op.exists(file1):
            print("Could not open %s" %file1)
            return None
        outname = op.join(op.dirname(filename),'Cu' 
                                          + op.basename(filename)[:-7]+'.fits')
        print("Making Cube image for %s" %op.basename(outname))
        F2 = fits.open(file2)
        F1 = fits.open(file1)
        data1 = F1[0].data
        data2 = F2[0].data
        a,b = data1.shape
        if a != len(ifucen[:,1]):
            return None
        data = np.vstack([data1,data2])
        x = np.arange(ifucen[:,1].min()-scale, ifucen[:,1].max()+scale, scale)
        y = np.arange(ifucen[:,2].min()-scale, ifucen[:,2].max()+scale, scale)
        xgrid, ygrid = np.meshgrid(x, y)
        zgrid = np.zeros((b,)+xgrid.shape)
        for k in xrange(b):
            for i in xrange(len(x)):
                for j in xrange(len(y)):
                    d = np.sqrt((ifucen[:,1] - xgrid[j,i])**2 + 
                                (ifucen[:,2] - ygrid[j,i])**2)
                    w = np.exp(-1./2.*(d/1.)**2)
                    sel = w > 1e-3
                    zgrid[k,j,i] = np.sum(data[sel,k]*w[sel])/np.sum(w[sel])
        hdu = fits.PrimaryHDU(zgrid)
        hdu.header['CDELT3'] = F1[0].header['CDELT1']
        hdu.header['CRVAL3'] = F1[0].header['CRVAL1']
        hdu.header['CRPIX3'] = F1[0].header['CRPIX1']
        hdu.writeto(outname, clobber=True)
    
def make_error_frame(image1, image2, mask1, mask2, header, outname):
    print("Making error image for %s" %op.basename(outname))
    a,b = image1.shape
    new = np.zeros((a*2,b))
    mas = np.zeros((a*2,b))

    new[:a,:] = image1
    new[a:,:] = image2
    mas[:a,:] = mask1
    mas[a:,:] = mask2
    err = np.zeros(new.shape)
    for i in xrange(2*a):
        err[i,:] = np.where(mas[i,:]<0, mas[i,:], 
                            biweight_filter(new[i,:], 21, 
                                            func=biweight_midvariance))
    hdu = fits.PrimaryHDU(err, header=header)
    hdu.header.remove('BIASSEC')
    hdu.header.remove('TRIMSEC')
    hdu.header['DATASEC'] = '[%i:%i,%i:%i]' %(1,b,1,2*a)
    hdu.writeto(outname, clobber=True)   
    
def make_fiber_image(Fe, header, outname, args, amp):
    print("Making Fiberextract image for %s" %op.basename(outname))
    a,b = Fe.shape
    hdu = fits.PrimaryHDU(Fe, header=header)
    hdu.header.remove('BIASSEC')
    hdu.header.remove('TRIMSEC')
    hdu.header['DATASEC'] = '[%i:%i,%i:%i]' %(1,b,1,a)
    hdu.header['CRVAL1'] = args.wvl_dict[amp][0]
    hdu.header['CDELT1'] = args.disp[amp]
    hdu.header['CD1_1'] = args.disp[amp]
    hdu.header['CRPIX1'] = 1
    hdu.writeto(outname, clobber=True)    
    
def make_spectrograph_image(image1, image2, header, outname):
    print("Making spectrograph image for %s" %op.basename(outname))
    a,b = image1.shape
    new = np.zeros((a*2,b))
    new[:a,:] = image1
    new[a:,:] = image2
    hdu = fits.PrimaryHDU(new, header=header)
    hdu.header.remove('BIASSEC')
    hdu.header.remove('TRIMSEC')
    hdu.header['DATASEC'] = '[%i:%i,%i:%i]' %(1,b,1,2*a)
    hdu.writeto(outname, clobber=True)    
            
def reduce_science(args):
    for spec in args.specid:
        spec_ind_sci = np.where(args.sci_df['Specid'] == spec)[0]
        for amp in config.Amps:
            amp_ind_sci = np.where(args.sci_df['Amp'] == amp)[0]
            sci_sel = np.intersect1d(spec_ind_sci, amp_ind_sci) 
            for ind in sci_sel:
                if args.instr == "virus":
                    ifucen = np.loadtxt(op.join(args.configdir, 'IFUcen_files', 
                                                args.ifucen_fn[amp][0]
                                                +args.sci_df['Ifuid'][ind]+'.txt'), 
                                                usecols=[0,1,2], 
                                                skiprows=args.ifucen_fn[amp][1])
                else:
                    ifucen = np.loadtxt(op.join(args.configdir, 'IFUcen_files', 
                                        args.ifucen_fn[amp][0]), 
                                usecols=[0,1,2], skiprows=args.ifucen_fn[amp][1])
                if args.debug:
                    print("Working on Sci for %s, %s" %(spec, amp))   
                sci1 = Amplifier(args.sci_df['Files'][ind],
                                 args.sci_df['Output'][ind],
                                 calpath=args.cal_dir, 
                                 debug=False, refit=False, dark_mult=1.0,
                                 darkpath=args.darkdir, biaspath=args.biasdir,
                                 virusconfig=args.configdir, specname=args.specname[amp])
                sci1.load_fibers()
                if sci1.fibers and not args.start_from_scratch:
                    if sci1.fibers[0].spectrum is not None:
                        sci1.get_image()
                        sci1.sky_subtraction()
                        sci1.clean_cosmics()
                else:                        
                    sci1.load_all_cal()
                    sci1.sky_subtraction()
                    sci1.clean_cosmics()
                    sci1.fiberextract(mask=sci1.mask)
                    sci1.sky_subtraction()
                sci2 = Amplifier(args.sci_df['Files'][ind].replace(amp, config.Amp_dict[amp][0]),
                                 args.sci_df['Output'][ind],
                                 calpath=args.cal_dir, 
                                 debug=False, refit=False, dark_mult=1.0,
                                 darkpath=args.darkdir, biaspath=args.biasdir,
                                 virusconfig=args.configdir, specname=args.specname[amp])
                sci2.load_fibers()
                if sci2.fibers and not args.start_from_scratch:
                    if sci2.fibers[0].spectrum is not None:
                        sci2.get_image()
                        sci2.sky_subtraction()
                        sci2.clean_cosmics()
                else:
                    sci2.load_all_cal()
                    sci2.sky_subtraction()
                    sci2.clean_cosmics()
                    sci2.fiberextract(mask=sci2.mask)
                    sci2.sky_subtraction()
                outname = op.join(args.sci_df['Output'][ind],
                                  'S%s_%s_sci_%s.fits' %(
                                  op.basename(args.sci_df['Files'][ind]).split('_')[0],
                                  args.sci_df['Ifuslot'][ind], config.Amp_dict[amp][1]))
                make_spectrograph_image(sci1.clean_image, sci2.clean_image, sci1.header, 
                           outname)
                outname = op.join(args.sci_df['Output'][ind],
                                  'e.S%s_%s_sci_%s.fits' %(
                                  op.basename(args.sci_df['Files'][ind]).split('_')[0],
                                  args.sci_df['Ifuslot'][ind], config.Amp_dict[amp][1]))
                make_error_frame(sci1.clean_image, sci2.clean_image, sci1.mask,
                                 sci2.mask, sci1.header, outname)
                outname = op.join(args.sci_df['Output'][ind],
                                  'cS%s_%s_sci_%s.fits' %(
                                  op.basename(args.sci_df['Files'][ind]).split('_')[0],
                                  args.sci_df['Ifuslot'][ind], config.Amp_dict[amp][1]))
                make_spectrograph_image(np.where(sci1.mask==0, 
                                                 sci1.clean_image, 0.0),
                                        np.where(sci2.mask==0, 
                                                 sci2.clean_image, 0.0),
                                        sci1.header, outname)
                Fe, FeS = recreate_fiberextract(sci1, sci2, wavelim=args.wvl_dict[amp], 
                                      disp=args.disp[amp])
                outname = op.join(args.sci_df['Output'][ind],
                                  'Fe%s_%s_sci_%s.fits' %(
                                  op.basename(args.sci_df['Files'][ind]).split('_')[0],
                                  args.sci_df['Ifuslot'][ind], config.Amp_dict[amp][1]))
                make_fiber_image(Fe, sci1.header, outname, args, amp)
                make_cube_file(args, outname, ifucen, args.cube_scale, 
                               config.Amp_dict[amp][1])
                outname = op.join(args.sci_df['Output'][ind],
                                  'FeS%s_%s_sci_%s.fits' %(
                                  op.basename(args.sci_df['Files'][ind]).split('_')[0],
                                  args.sci_df['Ifuslot'][ind], config.Amp_dict[amp][1]))
                make_fiber_image(FeS, sci1.header, outname, args, amp)
                make_cube_file(args, outname, ifucen, args.cube_scale, 
                               config.Amp_dict[amp][1])
                sci1.save_fibers()
                sci2.save_fibers()  
                if args.debug:
                    print("Finished working on Sci for %s, %s" %(spec, amp))                    
                

def reduce_twighlight(args):
    D = Distortion(op.join(args.configdir, 'DeformerDefaults', 
                                        'mastertrace_twi_027_L.dist'))   
    for spec in args.specid:
        spec_ind_twi = np.where(args.twi_df['Specid'] == spec)[0]
        for amp in config.Amps:
            amp_ind_twi = np.where(args.twi_df['Amp'] == amp)[0]
            twi_sel = np.intersect1d(spec_ind_twi, amp_ind_twi)
            for ind in twi_sel:
                if args.debug:
                    print("Working on Cal for %s, %s" %(spec, amp))                    
                twi1 = Amplifier(args.twi_df['Files'][ind],
                                 args.twi_df['Output'][ind],
                                 calpath=args.twi_df['Output'][ind], 
                                 debug=True, refit=True, dark_mult=0.0,
                                 darkpath=args.darkdir, biaspath=args.biasdir,
                                 virusconfig=args.configdir, specname=args.specname[amp])
                twi1.load_fibers()
                twi1.get_fiber_to_fiber(use_default_profile=False, 
                               init_lims=args.wvl_dict[amp], interactive=False,
                               check_fibermodel=True, check_wave=True,
                               fsize=args.fsize, bins=args.fibmodel_bins,
                               sigma=args.fibmodel_sig, power=args.fibmodel_pow)
                twi2 = Amplifier(args.twi_df['Files'][ind].replace(amp, config.Amp_dict[amp][0]),
                                 args.twi_df['Output'][ind],
                                 calpath=args.twi_df['Output'][ind], 
                                 debug=True, refit=True, dark_mult=0.0,
                                 darkpath=args.darkdir, biaspath=args.biasdir,
                                 virusconfig=args.configdir, specname=args.specname[amp])
                twi2.load_fibers()
                twi2.get_fiber_to_fiber(use_default_profile=False, 
                               init_lims=args.wvl_dict[amp], interactive=False,
                               check_fibermodel=True, check_wave=True, 
                               fsize=args.fsize, bins=args.fibmodel_bins,
                               sigma=args.fibmodel_sig, power=args.fibmodel_pow)
                image1 = get_model_image(twi1.image, twi1.fibers, 'fiber_to_fiber',
                                        debug=twi1.debug)
                image2 = get_model_image(twi2.image, twi2.fibers, 'fiber_to_fiber',
                                        debug=twi1.debug)
                outname = op.join(args.twi_df['Output'][ind], 
                                  'mastertrace_%s_%s.fits' 
                                  %(args.twi_df['Specid'][ind],
                                    config.Amp_dict[amp][1]))
                make_spectrograph_image(image1, image2, twi1.header, outname)
                outname = op.join(args.twi_df['Output'][ind], 
                                  'mastertwi_%s_%s.fits' 
                                  %(args.twi_df['Specid'][ind],
                                    config.Amp_dict[amp][1]))  
                make_spectrograph_image(twi1.image, twi2.image, twi1.header, outname)
                D = recalculate_dist_coeff(D, twi1, twi2)
                outname2 = op.join(args.twi_df['Output'][ind], 
                                  'mastertrace_%s_%s.dist' 
                                  %(args.twi_df['Specid'][ind],
                                    config.Amp_dict[amp][1]))
                D.writeto(outname2)
                twi1.save_fibers()
                twi2.save_fibers()
                if args.debug:
                    print("Finished working on Cal for %s, %s" %(spec, amp))  
                
def main():
    args = parse_args()
    if args.debug:
        t1 = time.time()
    if args.reduce_twi:
        reduce_twighlight(args)
    if args.reduce_sci:
        reduce_science(args)                                        
    if args.debug:
        t2=time.time()
        print("Total Time taken: %0.2f s" %(t2-t1))

if __name__ == '__main__':
    main()    
