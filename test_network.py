'''
    this is a simple test file
'''
import sys
sys.path.append('model')
sys.path.append('utils')

from utils_SH import *

# other modules
import os
import numpy as np

from torch.autograd import Variable
import torch
import cv2
import argparse

# This code is adapted from https://github.com/zhhoper/DPR

def parse_args():
    parser = argparse.ArgumentParser(
        description="image relighting training.")
    parser.add_argument(
        '--image',
        default='obama.jpg',
        help='name of image stored in data/',
    )
    parser.add_argument(
        '--model',
        default='trained.pt',
        help='model file to use stored in trained_model/'
    )
    parser.add_argument(
        '--gpu',
        action='store_true',
        help='cpu vs. gpu'
    )

    return parser.parse_args()


ARGS = parse_args()

# ---------------- create normal for rendering half sphere ------
img_size = 256
x = np.linspace(-1, 1, img_size)
z = np.linspace(1, -1, img_size)
x, z = np.meshgrid(x, z)

mag = np.sqrt(x**2 + z**2)
valid = mag <=1
y = -np.sqrt(1 - (x*valid)**2 - (z*valid)**2)
x = x * valid
y = y * valid
z = z * valid
normal = np.concatenate((x[...,None], y[...,None], z[...,None]), axis=2)
normal = np.reshape(normal, (-1, 3))
#-----------------------------------------------------------------

modelFolder = 'trained_models/'

# load model
from model import *
my_network = HourglassNet()
if (ARGS.gpu):
    my_network.load_state_dict(torch.load(os.path.join(modelFolder, ARGS.model)))
    my_network.cuda()
else:
    my_network.load_state_dict(torch.load(os.path.join(modelFolder, ARGS.model), map_location=torch.device('cpu')))
my_network.train(False)

lightFolder = 'data/test/light/'

saveFolder = 'result'
saveFolder = os.path.join(saveFolder, ARGS.model.split(".")[0])
if not os.path.exists(saveFolder):
    os.makedirs(saveFolder)

img = cv2.imread('data/test/images/{}'.format(ARGS.image))
row, col, _ = img.shape
img = cv2.resize(img, (256, 256))
Lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB) #converts image to one color space LAB

inputL = Lab[:,:,0] #taking only the L channel
inputL = inputL.astype(np.float32)/255.0 #normalise
inputL = inputL.transpose((0,1))
inputL = inputL[None,None,...] #not sure what's happening here
inputL = Variable(torch.from_numpy(inputL))
if ARGS.gpu:
    inputL = inputL.cuda()

def render_half_sphere(sh, output):
    sh = np.squeeze(sh)
    shading = get_shading(normal, sh)
    value = np.percentile(shading, 95)
    ind = shading > value
    shading[ind] = value
    shading = (shading - np.min(shading))/(np.max(shading) - np.min(shading))
    shading = (shading *255.0).astype(np.uint8)
    shading = np.reshape(shading, (256, 256))
    shading = shading * valid
    if output:
        cv2.imwrite(os.path.join(saveFolder,'light_predicted.png'.format(i)), shading)
    else: 
        cv2.imwrite(os.path.join(saveFolder,'light_{:02d}.png'.format(i)), shading)

for i in range(7):
    sh = np.loadtxt(os.path.join(lightFolder, 'rotate_light_{:02d}.txt'.format(i)))
    sh = sh[0:9]
    sh = sh * 0.5

    render_half_sphere(sh, False)

    #  rendering images using the network
    sh = np.reshape(sh, (1,9,1,1)).astype(np.float32)
    sh = Variable(torch.from_numpy(sh))
    if ARGS.gpu:
        sh = sh.cuda()
    #sh = Variable(torch.from_numpy(sh))


    outputImg, outputSH  = my_network(inputL, sh, 0)

    outputSH = outputSH.cpu().data.numpy()
    render_half_sphere(outputSH, True)

    outputImg = outputImg[0].cpu().data.numpy()
    outputImg = outputImg.transpose((1,2,0))
    outputImg = np.squeeze(outputImg)
    outputImg = (outputImg*255.0).astype(np.uint8)
    Lab[:,:,0] = outputImg
    resultLab = cv2.cvtColor(Lab, cv2.COLOR_LAB2BGR)
    resultLab = cv2.resize(resultLab, (col, row))
    img_name, e = os.path.splitext(ARGS.image)
    cv2.imwrite(os.path.join(saveFolder,
         '{}_{:02d}.jpg'.format(img_name,i)), resultLab)
    #----------------------------------------------