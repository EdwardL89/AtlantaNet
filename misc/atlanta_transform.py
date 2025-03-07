import os
import sys
import cv2
import time
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable


###focal_l set by default to 160 degrees over 1024x1024 footprint
fl = 90.27941412273405

class A2P(nn.Module):
    def __init__(self, equ_size=(512, 1024), out_dim=512, focal_l=fl, radius=90, up_flip=True, gpu=True):
        super(A2P, self).__init__()

        self.equ_h = equ_size[0]
        self.equ_w = equ_size[1]
        self.out_dim = out_dim
        
        self.radius = radius
        self.up_flip = up_flip
        self.gpu = gpu

        R_lst = []
        theta_lst = np.array([-90, 0, 90, 180], float) / 180 * np.pi
        phi_lst = np.array([90, -90], float) / 180 * np.pi

        for theta in theta_lst:
            angle_axis = theta * np.array([0, 1, 0], float)
            R = cv2.Rodrigues(angle_axis)[0]
            R_lst.append(R)

        for phi in phi_lst:
            angle_axis = phi * np.array([1, 0, 0], float)
            R = cv2.Rodrigues(angle_axis)[0]
            R_lst.append(R)

        if gpu:
            R_lst = [Variable(torch.FloatTensor(x)).cuda() for x in R_lst]
        else:
            R_lst = [Variable(torch.FloatTensor(x)) for x in R_lst]
        R_lst = R_lst[4:]
        
        equ_cx = (self.equ_w - 1) / 2.0
        equ_cy = (self.equ_h - 1) / 2.0
        c_x = (out_dim - 1) / 2.0
        c_y = (out_dim - 1) / 2.0

        f = focal_l

        w_len = radius / f * out_dim
                        
        cx = c_x
        cy = c_y
        self.intrisic = {
                    'f': f,
                    'cx': cx,
                    'cy': cy
                }

        interval = w_len / (out_dim - 1)
        
        z_map = np.zeros([out_dim, out_dim], float) + radius
        x_map = np.tile((np.arange(out_dim) - c_x) * interval, [out_dim, 1])
        y_map = np.tile((np.arange(out_dim) - c_y) * interval, [out_dim, 1]).T
        D = np.sqrt(x_map**2 + y_map**2 + z_map**2)
        xyz = np.zeros([out_dim, out_dim, 3], float)
        xyz[:, :, 0] = (radius / D) * x_map[:, :]
        xyz[:, :, 1] = (radius / D) * y_map[:, :]
        xyz[:, :, 2] = (radius / D) * z_map[:, :]

        if gpu:
            xyz = Variable(torch.FloatTensor(xyz)).cuda()
        else:
            xyz = Variable(torch.FloatTensor(xyz))
        self.xyz = xyz.clone()
        self.xyz = self.xyz.unsqueeze(0)
        self.xyz /= torch.norm(self.xyz, p=2, dim=3).unsqueeze(-1)

        reshape_xyz = xyz.view(out_dim * out_dim, 3).transpose(0, 1)
        self.loc = []
        self.grid = []
        for i, R in enumerate(R_lst):
            result = torch.matmul(R, reshape_xyz).transpose(0, 1)
            tmp_xyz = result.contiguous().view(1, out_dim, out_dim, 3)
            self.grid.append(tmp_xyz)
            lon = torch.atan2(result[:, 0] , result[:, 2]).view(1, out_dim, out_dim, 1) / np.pi
            lat = torch.asin(result[:, 1] / radius).view(1, out_dim, out_dim, 1) / (np.pi / 2)

            self.loc.append(torch.cat([lon, lat], dim=3))

    def forward(self, batch):
        batch_size = batch.size()[0]
                
        up_views = []
        down_views = []
        for i in range(batch_size):
            up_coor, down_coor = self.loc
            up_view = F.grid_sample(batch[i:i+1], up_coor)
            down_view = F.grid_sample(batch[i:i+1], down_coor)
            up_views.append(up_view)
            down_views.append(down_view)
        up_views = torch.cat(up_views, dim=0)
        if self.up_flip:
            up_views = torch.flip(up_views, dims=[2])
        down_views = torch.cat(down_views, dim=0)

        return up_views, down_views

    def GetGrid(self):
        return self.xyz   
        

if __name__ == '__main__':
    
    ##e2p = E2P((512, 1024), 512, 160, gpu=False)
    e2p = A2P(equ_size=(512, 1024), out_dim=1024, focal_l=90.2,radius=50, gpu=False)
    batch = torch.ones(4, 3, 512, 1024)
    [up, down] = e2p(batch)
    print (up.size())