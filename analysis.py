from database import *
import numpy as np
import yaml
import os
import shutil
import gpt as gpt
import tensorflow as tf
from natsort import natsorted
from tensorflow.keras.applications import MobileNetV2
# from tensorflow.keras.applications.mobilenet_v2 import preprocess_input, decode_predictions
from tensorflow.keras.preprocessing import image
from keras.applications.densenet import DenseNet121, preprocess_input, decode_predictions
import signal
import sys

db_path = "./public/sqlite.db"

if not os.path.exists(db_path):
    raise "could not found sqlite.db."

db.init(db_path)

db.connect(reuse_if_open=True)

# Tag.delete()

# model = DenseNet121(weights='imagenet')

# with open("./gallery/README.yml", 'r') as f:
#     y = yaml.safe_load(f)

# if not y:
#     raise "could not found README.yml"

# for d in y:
#     element = y[d]
#     url = element['url']
#     gallery_dir = f'gallery/{url}'
#     sorted_files = natsorted(os.listdir(gallery_dir))
#     # calc tags;
#     for img_name in sorted_files:
#         img_path = f'{gallery_dir}/{img_name}'
#         pathkey = f'{url}/{img_name}'
#         pic = Photo.get_or_none(path=pathkey)
#         if not pic:
#             continue
#         if pic.tag:
#             continue
#         img = image.load_img(img_path, target_size=(224, 224))
#         x = image.img_to_array(img)
#         x = np.expand_dims(x, axis=0)
#         x = preprocess_input(x)
#         preds = model.predict(x)
#         result = decode_predictions(preds, top=1)[0]
#         if not result:
#             continue
#         pred_label = result[0][1]
#         pred_num = result[0][2]
#         if pred_num < 0.55:
#             continue
#         print('Predicted:', img_path, result[0])
#         tag, _ = Tag.get_or_create(name=pred_label)
#         pic.tag = tag
#         pic.save()

# for d in y:
#     element = y[d]
#     url = element['url']
#     gallery_dir = f'gallery/{url}'
#     sorted_files = natsorted(os.listdir(gallery_dir))
#     index = 0
#     if index > 3:
#         continue
#     for img_name in sorted_files:
#         img_path = f'{gallery_dir}/{img_name}'
#         pathkey = f'{url}/{img_name}'
#         pic = Photo.get_or_none(path=pathkey)
#         if not pic:
#             continue
#         if pic.desc != ' - · - ':
#             continue
#         text = gpt.generate_desc(img_path)
#         print('Predicted:', img_path, "\n",  text)
#         pic.dsec = text
#         pic.save()
#         index += 1
def timeout(signum, frame):
    db.close()
    print("Time is up!")
    sys.exit(1)


def resolve():    
    photos_without_desc = Photo.select().where(Photo.desc == ' - · - ')
    for photo in photos_without_desc:
        print(f"Photo ID: {photo.id}, Path: {photo.path}, Description: {photo.desc}")
        img_path = f'gallery/{photo.path}'
        text = gpt.generate_desc(img_path)
        print('Predicted:', img_path, "\n",  text)
        photo.dsec = text
        photo.save()
    db.close()

# 4h
signal.signal(signal.SIGALRM, timeout)
signal.alarm(14400)

try:
    resolve()
except Exception as e:
    print("Program terminated due to timeout.")
    db.close()
