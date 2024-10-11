import kagglehub
# Download latest version


import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
from torchvision import datasets, transforms, models
from torch.utils.data import DataLoader
import numpy as np
import torchvision
import matplotlib.pyplot as plt
import time
from tqdm import tqdm
import os
from PIL import Image
from tempfile import TemporaryDirectory
import torch.backends.cudnn as cudnn

cudnn.benchmark = True
plt.ion()

import mlflow
from torchinfo import summary


# Data augmentation and normalization for training
# Just normalization for validation
data_transforms = {
    'Training': transforms.Compose([
        transforms.RandomResizedCrop(224),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
    'Testing': transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ]),
}



def train_model(model, criterion, optimizer, scheduler, num_epochs=25):
    since = time.time()

    # Create a temporary directory to save training checkpoints
    with TemporaryDirectory() as tempdir:
        best_model_params_path = os.path.join(tempdir, 'best_model_params.pt')

        torch.save(model.state_dict(), best_model_params_path)
        best_acc = 0.0

        for epoch in range(num_epochs):
            print(f'Epoch {epoch}/{num_epochs - 1}')
            print('-' * 10)

            # Each epoch has a training and validation phase
            for phase in ['Training', 'Testing']:
                if phase == 'Training':
                    model.train()  # Set model to training mode
                else:
                    model.eval()   # Set model to evaluate mode

                running_loss = 0.0
                running_corrects = 0

                # Iterate over data.
                for inputs, labels in tqdm(dataloaders[phase]):
                    inputs = inputs.to(device)
                    labels = labels.to(device)

                    # zero the parameter gradients
                    optimizer.zero_grad()

                    # forward
                    # track history if only in train
                    with torch.set_grad_enabled(phase == 'Training'):
                        outputs = model(inputs)
                        _, preds = torch.max(outputs, 1)
                        loss = criterion(outputs, labels)

                        # backward + optimize only if in training phase
                        if phase == 'Training':
                            loss.backward()
                            optimizer.step()

                    # statistics
                    running_loss += loss.item() * inputs.size(0)
                    running_corrects += torch.sum(preds == labels.data)
                if phase == 'Training':
                    scheduler.step()

                epoch_loss = running_loss / dataset_sizes[phase]
                epoch_acc = running_corrects.double() / dataset_sizes[phase]

                print(f'{phase} Loss: {epoch_loss:.4f} Acc: {epoch_acc:.4f}')

                if phase == 'Training':
                    mlflow.log_metric("Training loss", f"{epoch_loss:.4f}",step=epoch)
                    mlflow.log_metric("Training accuracy", f"{epoch_acc:.4f}", step=epoch)

                else:
                    mlflow.log_metric("Testing loss", f"{epoch_loss:.4f}",step=epoch)
                    mlflow.log_metric("Testing accuracy", f"{epoch_acc:.4f}", step=epoch)

                # deep copy the model
                if phase == 'Testing' and epoch_acc > best_acc:
                    best_acc = epoch_acc
                    torch.save(model.state_dict(), best_model_params_path)

            print()

        time_elapsed = time.time() - since
        print(f'Training complete in {time_elapsed // 60:.0f}m {time_elapsed % 60:.0f}s')
        print(f'Best val Acc: {best_acc:4f}')

        # load best model weights
        model.load_state_dict(torch.load(best_model_params_path, weights_only=True))
    #return model

if __name__ == '__main__':

    path = kagglehub.dataset_download("sartajbhuvaji/brain-tumor-classification-mri")

    data_dir = path
    image_datasets = {x: datasets.ImageFolder(os.path.join(data_dir, x),
                                            data_transforms[x])
                    for x in ['Training', 'Testing']}
    print(image_datasets)

    dataloaders = {x: torch.utils.data.DataLoader(image_datasets[x], batch_size=4,
                                                shuffle=True, num_workers=4)
                for x in ['Training', 'Testing']}

    print(dataloaders)

    dataset_sizes = {x: len(image_datasets[x]) for x in ['Training', 'Testing']}
    print(dataset_sizes)

    class_names = image_datasets['Training'].classes
    print(class_names)

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print(device)


    model_ft = models.resnet18(weights='IMAGENET1K_V1')
    num_ftrs = model_ft.fc.in_features
    # Alternatively, it can be generalized to ``nn.Linear(num_ftrs, len(class_names))``.
    model_ft.fc = nn.Linear(num_ftrs, len(class_names))

    model_ft = model_ft.to(device)
    criterion = nn.CrossEntropyLoss()

    # Observe that all parameters are being optimized
    optimizer_ft = optim.SGD(model_ft.parameters(), lr=0.001, momentum=0.9)

    # Decay LR by a factor of 0.1 every 7 epochs
    exp_lr_scheduler = lr_scheduler.StepLR(optimizer_ft, step_size=7, gamma=0.1)
    num_epochs = 10

    with mlflow.start_run():
        params = {
            "epochs":num_epochs,
            "Optimizer":"SGD"
        }

        # log training parameters
        mlflow.log_params(params)

        # log model summary
        with open("model_summary.txt", "w", encoding='utf-8') as f:
            f.write(str(summary(model_ft)))
        mlflow.log_artifact("model_summary.txt")

        #model_ft = train_model(model_ft, criterion, optimizer_ft, exp_lr_scheduler,
        #                   num_epochs=num_epochs)
        train_model(model_ft, criterion, optimizer_ft, exp_lr_scheduler,num_epochs=num_epochs)

        # save the trained model to mlflow
        mlflow.pytorch.log_model(model_ft, "model")