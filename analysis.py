from database import *
import numpy as np
import yaml
import os
import tensorflow as tf
from natsort import natsorted
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input, decode_predictions
from tensorflow.keras.preprocessing import image

db_path = "./thumbnail_public/sqlite.db"

if not os.path.exists(db_path):
    raise "could not found sqlite.db."

db.init(db_path)

db.connect(reuse_if_open=True)

model = MobileNetV2(weights='imagenet')

with open("./thumbnail_public/README.yml", 'r') as f:
    y = yaml.safe_load(f)

if not y:
    raise "could not found README.yml"

for d in y:
    element = y[d]
    url = element['url']
    gallery_dir = f'thumbnail_public/{url}'
    sorted_files = natsorted(os.listdir(gallery_dir))
    for img_name in sorted_files:
        img_path = f'{gallery_dir}/{img_name}'
        img = image.load_img(img_path, target_size=(224, 224))
        x = image.img_to_array(img)
        x = np.expand_dims(x, axis=0)
        x = preprocess_input(x)
        preds = model.predict(x)
        pathkey = f'{url}/{img_name}'
        pic = Photo.get_or_none(path=pathkey)
        if not pic or pic.tag is not None:
            continue
        result = decode_predictions(preds, top=1)[0]
        if not result:
            continue
        pred_label = result[0][1]
        print('Predicted:', img_path, pred_label)
        tag, _ = Tag.get_or_create(name=pred_label)
        pic.tag = tag
        pic.save()

db.close()