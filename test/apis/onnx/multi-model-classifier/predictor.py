import os
import numpy as np
import onnxruntime as rt
import cv2, requests
from scipy.special import softmax


def get_url_image(url_image):
    """
    Get numpy image from URL image.
    """
    resp = requests.get(url_image, stream=True).raw
    image = np.asarray(bytearray(resp.read()), dtype="uint8")
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)
    return image


def image_resize(image, width=None, height=None, inter=cv2.INTER_AREA):
    """
    Resize a numpy image.
    """
    dim = None
    (h, w) = image.shape[:2]

    if width is None and height is None:
        return image

    if width is None:
        # calculate the ratio of the height and construct the dimensions
        r = height / float(h)
        dim = (int(w * r), height)
    else:
        # calculate the ratio of the width and construct the dimensions
        r = width / float(w)
        dim = (width, int(h * r))

    resized = cv2.resize(image, dim, interpolation=inter)

    return resized


def preprocess(img_data):
    """
    Normalize input for inference.
    """
    # move pixel color dimension to position 0
    img = np.moveaxis(img_data, 2, 0)

    mean_vec = np.array([0.485, 0.456, 0.406])
    stddev_vec = np.array([0.229, 0.224, 0.225])
    norm_img_data = np.zeros(img.shape).astype("float32")
    for i in range(img.shape[0]):
        # for each pixel in each channel, divide the value by 255 to get value between [0, 1] and then normalize
        norm_img_data[i, :, :] = (img[i, :, :] / 255 - mean_vec[i]) / stddev_vec[i]

    # extend to batch size of 1
    norm_img_data = norm_img_data[np.newaxis, ...]
    return norm_img_data


def postprocess(results):
    """
    Eliminates all dimensions of size 1, softmaxes the input and then returns the index of the element with the highest value.
    """
    squeezed = np.squeeze(results)
    maxed = softmax(squeezed)
    result = np.argmax(maxed)
    return result


class Handler:
    def __init__(self, model_client, config):
        # onnx client
        self.client = model_client

        # for image classifiers
        classes = requests.get(config["image-classifier-classes"]).json()
        self.image_classes = [classes[str(k)][1] for k in range(len(classes))]
        self.resize_value = config["image-resize"]

    def handle_post(self, payload, query_params):
        # get request params
        model_name = query_params["model"]
        img_url = payload["url"]

        # process the input
        img = get_url_image(img_url)
        img = image_resize(img, height=self.resize_value)
        img = preprocess(img)

        # predict
        model = self.client.get_model(model_name)
        session = model["session"]
        input_name = model["input_name"]
        output_name = model["output_name"]
        input_dict = {
            input_name: img,
        }
        results = session.run([output_name], input_dict)[0]

        # interpret result
        result = postprocess(results)
        predicted_label = self.image_classes[result]

        return {"label": predicted_label}

    def load_model(self, model_path):
        """
        Load ONNX model from disk.
        """

        model_path = os.path.join(model_path, os.listdir(model_path)[0])
        session = rt.InferenceSession(model_path)
        return {
            "session": session,
            "input_name": session.get_inputs()[0].name,
            "output_name": session.get_outputs()[0].name,
        }
