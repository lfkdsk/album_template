from transformers import AutoModelForCausalLM, AutoTokenizer
from PIL import Image

model_id = "vikhyatk/moondream2"
revision = "2024-04-02"
model = AutoModelForCausalLM.from_pretrained(
    model_id, trust_remote_code=True, revision=revision
)
tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)

def generate_desc(url):
    image = Image.open(url)
    # image = image.resize((224, 224), Image.ANTIALIAS)
    enc_image = model.encode_image(image)
    return model.answer_question(enc_image, "Enjoy the picture.", tokenizer)