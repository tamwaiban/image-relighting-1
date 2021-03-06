#!/usr/bin/env python
#coding: utf8

import sys
sys.path.append('model')
sys.path.append('utils')

import cv2 
import time
import math
import numpy as np
from scipy import ndimage
from skimage import io
from skimage import img_as_float, img_as_ubyte
from skimage.color import rgb2gray

import sys
import os

from torch.autograd import Variable
import torch
import argparse

from model import *

def parse_args():
    parser = argparse.ArgumentParser(
        description="live image relighting")
    parser.add_argument(
        '--light_image',
        default=None,
        help='path to image light to copy',
    )
    parser.add_argument(
        '--light_text',
        default=None,
        help='path to lighting matrix to copy',
    )
    parser.add_argument(
        '--input_path',
        default=None,
        help='specify a path to a video to be relit, instead of the webcam'
    )
    parser.add_argument(
        '--output_path',
        default='output.avi',
        help='specify path to write output video to, if input was specified'
    )
    
    return parser.parse_args()


def preprocess_image(img):
    row, col, _ = img.shape
    img = cv2.resize(img, (256, 256))
    Lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB) #converts image to one color space LAB

    inputL = Lab[:,:,0] #taking only the L channel
    inputL = inputL.astype(np.float32)/255.0 #normalise
    inputL = inputL.transpose((0,1))
    inputL = inputL[None,None,...] #not sure what's happening here

    inputL = Variable(torch.from_numpy(inputL))
    return inputL, row, col, Lab

def relight_image(model, src_img, target):
    src_img, row, col, Lab = preprocess_image(src_img)

    outputImg, _ = model(src_img, target, 0)

    outputImg = outputImg[0].cpu().data.numpy()
    outputImg = outputImg.transpose((1,2,0))
    outputImg = np.squeeze(outputImg)
    outputImg = (outputImg*255.0).astype(np.uint8)
    Lab[:,:,0] = outputImg
    resultLab = cv2.cvtColor(Lab, cv2.COLOR_LAB2BGR)
    resultLab = cv2.resize(resultLab, (col, row))
    return resultLab

class live_transfer_handler():
    """
    This function shows the live Fourier transform of a continuous stream of 
    images captured from an attached camera.

    """

    wn = "Image Lighting Transfer"
    use_camera = True
    im = 0
    model = 0
    target = None

    def __init__(self, target_img_path, target_text_path, input_path, **kwargs):        
        # Camera device
        if (input_path is not None):
            self.vc = cv2.VideoCapture(input_path)
        else:
            self.vc = cv2.VideoCapture(0)

        if not self.vc.isOpened():
            print( "No camera found or error opening camera." )
            self.use_camera = False
            return
    
        else:
            # We found a camera!
            # Requested camera size. This will be cropped square later on, e.g., 240 x 240
            if (input_path is None):
                # Set the size of the output window

                self.vc.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                self.vc.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                cv2.namedWindow(self.wn, 0)            

        # load model
        my_network = HourglassNet()
        my_network.load_state_dict(torch.load("trained_models/trained.pt", map_location=torch.device('cpu')))
        my_network.train(False)
        self.model = my_network

        # load target
        if target_img_path: 
            target_img = cv2.imread(target_img_path)
            light_img, _, _, _ = preprocess_image(target_img)
            sh = torch.zeros((1,9,1,1))
            _, outputSH  = self.model(light_img, sh, 0)
            self.target = outputSH

        elif target_text_path: 
            sh = np.loadtxt(target_text_path)
            sh = sh[0:9]
            sh = sh * 0.5
            sh = np.reshape(sh, (1,9,1,1)).astype(np.float32)
            outputSH = Variable(torch.from_numpy(sh))
            self.target = outputSH

        else: 
            print("No target specified")
            return

        videoWriter = None
        if (ARGS.output_path is not None):
            _, img = self.vc.read()
            dim1 = img.shape[0]
            dim2 = img.shape[1]
            #for now I am fixing this as a square because it gets better results
            videoWriter = cv2.VideoWriter(ARGS.output_path,cv2.VideoWriter_fourcc(*'MJPG'), 30, (dim1,dim1)) #change to dim2, dim1 to output not a square

        #if flag is true, pass to relighter
        # Main loop
        end = False
        while not end:
            a = time.perf_counter()
            end = self.relighter(videoWriter)
            if (ARGS.input_path is None):
                print('framerate = {} fps \r'.format(1. / (time.perf_counter() - a)))
    
        if self.use_camera:
            # Stop camera
            self.vc.release()

    def relighter(self, writer = None):

        if self.use_camera:
            # Read image
            _, im = self.vc.read()
            if im is None:
                writer.release()
                return True
            
            # if ARGS.input_path is None:
            if True: #for now I am fixing this as a square because it gets better results
                if im.shape[1] > im.shape[0]:
                    cropx = int((im.shape[1]-im.shape[0])/2)
                    cropy = 0
                elif im.shape[0] > im.shape[1]:
                    cropx = 0
                    cropy = int((im.shape[0]-im.shape[1])/2)

                self.im = im[cropy:im.shape[0]-cropy, cropx:im.shape[1]-cropx]

            else:
                self.im = im

        if (ARGS.input_path is None):
            # Set size
            width = 256
            height = 256
            cv2.resizeWindow(self.wn, width*2, height*2)

        real = img_as_float(self.im)
        relit = relight_image(self.model, self.im, self.target)
        relit = img_as_float(relit)
        output = np.clip(np.concatenate((real,relit),axis = 1),0,1)


        if writer is not None:
            frame = (relit*255).astype('uint8')
            writer.write(frame)

        if (ARGS.input_path is None):
            cv2.imshow(self.wn, relit)
            cv2.waitKey(1)

        return

ARGS = parse_args()

live_transfer_handler(ARGS.light_image, ARGS.light_text, ARGS.input_path)