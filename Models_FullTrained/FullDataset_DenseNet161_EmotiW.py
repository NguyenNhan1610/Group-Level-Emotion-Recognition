#----------------------------------------------------------------------------
# IMPORTING MODULES
#----------------------------------------------------------------------------

from __future__ import print_function, division

import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, utils
from torch.autograd import Variable

from PIL import Image

import numpy as np
import torchvision
from torchvision import datasets, models, transforms
import time
import os
import copy
import pickle

#---------------------------------------------------------------------------
# IMPORTANT PARAMETERS
#---------------------------------------------------------------------------

root_dir = "../Dataset/"
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
epochs = 16
batch_size = 32
maxFaces = 15
numClasses = 3

#---------------------------------------------------------------------------
# DATASET AND LOADERS
#---------------------------------------------------------------------------

neg_train = sorted(os.listdir('../Dataset/emotiw/train/'+'Negative/'))
neu_train = sorted(os.listdir('../Dataset/emotiw/train/'+'Neutral/'))
pos_train = sorted(os.listdir('../Dataset/emotiw/train/'+'Positive/'))

train_filelist = neg_train + neu_train + pos_train

val_filelist = []
test_filelist = []

with open('../Dataset/val_list', 'rb') as fp:
    val_filelist = pickle.load(fp)

with open('../Dataset/test_list', 'rb') as fp:
    test_filelist = pickle.load(fp)

for i in train_filelist:
    if i[0] != 'p' and i[0] != 'n':
        train_filelist.remove(i)
        
for i in val_filelist:
    if i[0] != 'p' and i[0] != 'n':
        val_filelist.remove(i)

for i in range(len(train_filelist)):
    train_filelist[i] = 'train/' + train_filelist[i]

for i in range(len(val_filelist)):
    val_filelist[i] = 'val/' + val_filelist[i]

for i in range(len(test_filelist)):
    test_filelist[i] = 'val/' + test_filelist[i]

full_train_filelist = train_filelist + val_filelist
full_val_filelist = test_filelist

dataset_sizes = [len(full_train_filelist), len(full_val_filelist)]
print(dataset_sizes)

train_global_data_transform = transforms.Compose([
        transforms.RandomResizedCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

val_global_data_transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

class EmotiWDataset(Dataset):
    
    def __init__(self, filelist, root_dir, transformGlobal=transforms.ToTensor(), transformFaces = transforms.ToTensor()):
        """
        Args:
            filelist: List of names of image/feature files.
            root_dir: Dataset directory
            transform (callable, optional): Optional transformer to be applied
                                            on an image sample.
        """
        
        self.filelist = filelist
        self.root_dir = root_dir
        self.transformGlobal = transformGlobal
        self.transformFaces = transformFaces
            
    def __len__(self):
        return (len(self.filelist)) 
 
    def __getitem__(self, idx):
        
        folder_name, filename = self.filelist[idx].split('/')[0], self.filelist[idx].split('/')[1].split('.')[0]
        # filename = self.filelist[idx].split('.')[0]
        labeldict = {'neg':'Negative',
                     'neu':'Neutral',
                     'pos':'Positive',
                     'Negative': 0,
                     'Neutral': 1,
                     'Positive':2}

        labelname = labeldict[filename.split('_')[0]]

        #IMAGE 

        image = Image.open(self.root_dir+'emotiw/'+folder_name+'/'+labelname+'/'+filename+'.jpg')
        if self.transformGlobal:
            image = self.transformGlobal(image)
        if image.shape[0] == 1:
            image_1 = np.zeros((3, 224, 224), dtype = float)
            image_1[0] = image
            image_1[1] = image
            image_1[2] = image
            image = image_1
            image = torch.FloatTensor(image.tolist()) 
        
        #SAMPLE
        sample = {'image': image, 'label':labeldict[labelname]}
        return sample


train_dataset = EmotiWDataset(full_train_filelist, root_dir, transformGlobal=train_global_data_transform)

train_dataloader = DataLoader(train_dataset, shuffle=True, batch_size=batch_size, num_workers=0)

val_dataset = EmotiWDataset(full_val_filelist, root_dir, transformGlobal = val_global_data_transform)

val_dataloader = DataLoader(val_dataset, shuffle =True, batch_size = batch_size, num_workers = 0)

print('Dataset Loaded')

#---------------------------------------------------------------------------
# MODEL DEFINITION
#---------------------------------------------------------------------------


model_ft = models.densenet161(pretrained=True)
num_ftrs = model_ft.classifier.in_features
model_ft.classifier = nn.Linear(num_ftrs, 3)

model_ft = model_ft.to(device)

#---------------------------------------------------------------------------
# TRAINING
#---------------------------------------------------------------------------

def train_model(model, criterion, optimizer, scheduler, num_epochs = 25):
    
    since = time.time()
    
    best_model_wts = copy.deepcopy(model.state_dict())
    best_acc = 0.0
    
    for epoch in range(num_epochs):
        print("Epoch {}/{}".format(epoch, num_epochs - 1))
        print('-' * 10)
        
        for phase in range(2):
            if phase == 0:
                dataloaders = train_dataloader
                scheduler.step()
                model.train()
            else:
                dataloaders = val_dataloader
                model.eval()
            
            running_loss = 0.0
            running_corrects = 0
            
            for i_batch, sample_batched in enumerate(dataloaders):
                inputs = sample_batched['image']
                labels = sample_batched['label']

                inputs = inputs.to(device)
                labels = labels.to(device)
                
                optimizer.zero_grad()
                
                with torch.set_grad_enabled(phase == 0):
                    outputs = model(inputs)
                    _, preds = torch.max(outputs, 1)
                    loss = criterion(outputs, labels)
                    
                    if phase == 0:
                        loss.backward()
                        optimizer.step()
                
                running_loss += loss.item() * inputs.size(0)
                running_corrects += torch.sum(preds == labels.data)
                
            epoch_loss = running_loss / dataset_sizes[phase]
            epoch_acc = running_corrects.double() / dataset_sizes[phase]
            
            print('{} Loss: {:.4f} Acc: {:.4f}'.format(
                phase, epoch_loss, epoch_acc))
            
            if phase == 1 and epoch_acc > best_acc:
                best_acc = epoch_acc
                best_model_wts = copy.deepcopy(model.state_dict())
                torch.save(model_ft, '../TrainedModels/FullDataset/DenseNet161_EmotiW')

        
        print()
    time_elapsed = time.time() - since
    print('Training complete in {: .0f}m {:0f}s'.format(
        time_elapsed // 60, time_elapsed % 60))
    print('Best val Acc: {:.4f}'.format(best_acc))
    
    model.load_state_dict(best_model_wts)
    return model

criterion = nn.CrossEntropyLoss()

optimizer_ft = optim.SGD(model_ft.parameters(), lr = 0.001, momentum=0.9)

exp_lr_scheduler = lr_scheduler.StepLR(optimizer_ft, step_size=7, gamma=0.1)

model_ft = train_model(model_ft, criterion, optimizer_ft, 
                      exp_lr_scheduler, num_epochs=epochs)

torch.save(model_ft, '../TrainedModels/FullDataset/DenseNet161_EmotiW')