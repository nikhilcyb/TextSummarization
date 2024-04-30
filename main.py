# -*- coding: utf-8 -*-
"""Main.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/19QyXBFMqnGT-K0Vc9LjCIOg6UqCEjH6S

**Installing All Requirements:**
"""

!pip install torch torchvision transformers datasets rouge nltk tensorboard gradio SentencePiece
!pip install transformers[torch]
!pip install accelerate -U
!pip install rouge

import torch
import os
import json
from transformers import T5ForConditionalGeneration, T5Tokenizer, T5Config
from datasets import load_dataset
from transformers import TextDataset, DataCollatorForLanguageModeling
from transformers import Trainer, TrainingArguments
from rouge import Rouge
import nltk
import gradio as gr
import matplotlib.pyplot as plt
from torch.utils.tensorboard import SummaryWriter
from transformers import AdamW
from transformers import get_scheduler
from transformers import EarlyStoppingCallback
from transformers.optimization import AdamW, get_linear_schedule_with_warmup

from nltk.corpus import stopwords
from nltk import pos_tag
from nltk.tokenize import word_tokenize
from nltk.corpus import wordnet

nltk.download("stopwords")
nltk.download("punkt")
nltk.download("wordnet")
nltk.download('averaged_perceptron_tagger')

"""**Loading CNN-DailyMail Dataset**"""

# Step 1: Load the CNN/Daily Mail dataset using load_dataset
cnn_daily_mail = load_dataset("cnn_dailymail",'3.0.0')

# Access the training split
train_dataset = cnn_daily_mail["train"]

# Access the validation split
validation_dataset = cnn_daily_mail["validation"]

# Access the test split
test_dataset = cnn_daily_mail["test"]

"""**Preprocessing For Dataset**"""

# Step 2: Preprocess the data according to t5 model for abstractive text summarization
tokenizer = T5Tokenizer.from_pretrained("t5-small")

tokenizer.pad_token = tokenizer.eos_token

def get_wordnet_pos(treebank_tag):
    if treebank_tag.startswith('J'):
        return wordnet.ADJ
    elif treebank_tag.startswith('V'):
        return wordnet.VERB
    elif treebank_tag.startswith('N'):
        return wordnet.NOUN
    elif treebank_tag.startswith('R'):
        return wordnet.ADV
    else:
        return wordnet.NOUN  # Default to noun if the POS tag is not found

def preprocess_example(source_text, target_text, max_seq_length=512):

 # Tokenization
    source_tokens = word_tokenize(source_text)
    target_tokens = word_tokenize(target_text)

    # Filter out stop words
    source_tokens = [token for token in source_tokens if token.lower() not in stop_words]

    # Part-of-speech tagging
    source_pos_tags = pos_tag(source_tokens)
    target_pos_tags = pos_tag(target_tokens)

    # Lemmatization
    lemmatizer = nltk.WordNetLemmatizer()
    lemmatized_source_tokens = [lemmatizer.lemmatize(token, get_wordnet_pos(tag))
                                 for token, tag in source_pos_tags]
    lemmatized_target_tokens = [lemmatizer.lemmatize(token, get_wordnet_pos(tag))
                                 for token, tag in target_pos_tags]

    # Token IDs using tokenizer
    input_ids = tokenizer.encode(lemmatized_source_tokens, truncation=True, max_length=max_seq_length)
    label_ids = tokenizer.encode(lemmatized_target_tokens, truncation=True, max_length=max_seq_length)

    # Ensure PyTorch tensors
    input_ids = torch.tensor(input_ids)
    attention_mask = (input_ids != tokenizer.pad_token_id).long()  # Convert to long type
    label_ids = torch.tensor(label_ids)

    return {
        'input_ids': input_ids,
        'attention_mask': attention_mask,
        'labels': label_ids,
    }

# Define or import stop words
stop_words = set(stopwords.words('english'))

def fine_tune_T5(model_name, train_file, validation_file, test_file, output_dir):
    # Load model and tokenizer
    model = T5ForConditionalGeneration.from_pretrained(model_name)
    tokenizer = T5Tokenizer.from_pretrained(model_name)

    # Load training dataset
    train_dataset = TextDataset(
        tokenizer=tokenizer,
        file_path=train_file,
        block_size=128
    )
    validation_dataset = TextDataset(
        tokenizer=tokenizer,
        file_path=validation_file,
        block_size=128
    )

    # Load test dataset
    test_dataset = TextDataset(
        tokenizer=tokenizer,
        file_path=test_file,
        block_size=128
    )

    # Create data collator for language modeling
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer, mlm=False
    )

    # Define training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=5,
        per_device_train_batch_size=50,
        per_device_eval_batch_size=25,
        warmup_steps=500,
        weight_decay=0.01,
        save_steps=10000,
        evaluation_strategy="epoch",
        logging_strategy="epoch",
        logging_dir="./logs",
        logging_steps=1000,  # Set a specific value for how often to log
        report_to="tensorboard",  # Set the reporting backend to TensorBoard
    )

    # Create optimizer and scheduler
    optimizer = AdamW(model.parameters(), lr=5e-5)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=500, num_training_steps=len(train_dataset) * training_args.num_train_epochs)

    # Train the model
    trainer = Trainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        data_collator=data_collator,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        optimizers=(optimizer, scheduler)  # Add optimizer and scheduler to Trainer
    )

    # Fine-tune the model and save training and validation losses
    training_losses = trainer.train()
    validation_losses = trainer.evaluate()

    # Save the losses to files
    torch.save(training_losses, "training_loss.pt")
    torch.save(validation_losses, "validation_loss.pt")

    # Print information about the test file
    print(f"Test file: {test_dataset}")

    # Print the current working directory
    print(f"Current working directory: {os.getcwd()}")

    # Save the fine-tuned model
    trainer.save_model(f"/content/gdrive/MyDrive/ATS/{output_dir}")
    tokenizer.save_pretrained(f"/content/gdrive/MyDrive/ATS/{output_dir}")

"""**Selection of Samples from dataset**"""

def select_consecutive_examples(dataset, start_index, num_examples):
    selected_examples = []
    while len(selected_examples) < num_examples:
        example = dataset[start_index]
        if example not in selected_examples:
            selected_examples.append(example)
        start_index += 1  # Move to the next example
    return selected_examples

def save_preprocessed_data_to_txt(data, filename):
  with open(filename, "w") as f:
    for example in data:
      example_string = str(example)
      f.write(example_string + "\n")

def load_t5_model(model_name="t5-small"):
    model = T5ForConditionalGeneration.from_pretrained(model_name)
    tokenizer = T5Tokenizer.from_pretrained(model_name)
    return model, tokenizer

def load_our_model(model_name):
    model = T5ForConditionalGeneration.from_pretrained(model_name)
    tokenizer = T5Tokenizer.from_pretrained(model_name)
    return model, tokenizer

def generate_summary(model, tokenizer, input_text):
    input_ids = tokenizer.encode("summarize: " + input_text, return_tensors="pt", max_length=512, truncation=True)
    summary_ids = model.generate(input_ids, max_length=150, length_penalty=0.8, num_beams=4, early_stopping=True)

    summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True, clean_up_tokenization_spaces=True)
    return summary

def gradio_interface(model, tokenizer):
    def summarization(input_text):
        summary = generate_summary(model, tokenizer, input_text)
        return summary

    iface = gr.Interface(fn=summarization, inputs="text", outputs="text",live = True)
    iface.launch()

!pip install rouge
from rouge import Rouge

from rouge import Rouge
import json
import pandas as pd

def calculate_rouge_scores(model, tokenizer, test_dataset_path):
    rouge = Rouge()
    references = []
    predictions = []

    for example in test_dataset:
        input_text = example["article"]
        target_summary = example["highlights"]

        # Generate summary using the fine-tuned model
        summary = generate_summary(model, tokenizer, input_text)

        references.append(target_summary)
        predictions.append(summary)

    scores = rouge.get_scores(predictions, references, avg=True)
    return scores

def rouge_scores_to_dataframe(rouge_scores):
    # Convert ROUGE scores to a Pandas DataFrame
    df = pd.DataFrame(rouge_scores).transpose()
    df.columns = ['precision', 'recall', 'f1']
    return df

#Stage1
# Select consecutive examples from the training dataset.
start_index_train = 10000  # Adjust the starting index as needed
selected_train_examples = select_consecutive_examples(train_dataset, start_index_train, 5000)

# Select consecutive examples from the validation dataset.
start_index_valid = 1000  # Adjust the starting index as needed
selected_valid_examples = select_consecutive_examples(validation_dataset, start_index_valid, 500)

# Select consecutive examples from the test dataset.
start_index_test = 1000  # Adjust the starting index as needed
selected_test_examples = select_consecutive_examples(test_dataset, start_index_test, 500)

preprocessed_train_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_train_examples]
preprocessed_validation_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_valid_examples]
preprocessed_test_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_test_examples]

print(f"\nPreprocessed")
print(f"Training dataset size: {len(preprocessed_train_data)}")
print(f"Validation dataset size: {len(preprocessed_validation_data)}")
print(f"Test dataset size: {len(preprocessed_test_data)}")

# Save the preprocessed training data.
save_preprocessed_data_to_txt(preprocessed_train_data, "stage1_train_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_validation_data, "stage1_validation_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_test_data, "stage1_test_data.json")

# Fine-tune the model stage1
fine_tune_T5("t5-small", "/content/stage1_train_data.json","/content/stage1_validation_data.json","/content/stage1_test_data.json", "stage1_Model")

#Stage2
# Select consecutive examples from the training dataset.
start_index_train = 10000  # Adjust the starting index as needed
selected_train_examples = select_consecutive_examples(train_dataset, start_index_train, 5000)

# Select consecutive examples from the validation dataset.
start_index_valid = 1000  # Adjust the starting index as needed
selected_valid_examples = select_consecutive_examples(validation_dataset, start_index_valid, 500)

# Select consecutive examples from the test dataset.
start_index_test = 1000  # Adjust the starting index as needed
selected_test_examples = select_consecutive_examples(test_dataset, start_index_test, 200)

preprocessed_train_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_train_examples]
preprocessed_validation_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_valid_examples]
preprocessed_test_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_test_examples]

print(f"\nPreprocessed")
print(f"Training dataset size: {len(preprocessed_train_data)}")
print(f"Validation dataset size: {len(preprocessed_validation_data)}")
print(f"Test dataset size: {len(preprocessed_test_data)}")

# Save the preprocessed training data.
save_preprocessed_data_to_txt(preprocessed_train_data, "stage2_train_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_validation_data, "stage2_validation_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_test_data, "stage2_test_data.json")

# Fine-tune the model stage2
fine_tune_T5("/content/drive/MyDrive/ATS/stage1_Model", "/content/stage2_train_data.json","/content/stage2_validation_data.json","/content/stage2_test_data.json", "stage2_Model")

print("STAGE-2 ROUGE Scores:\n")

model, tokenizer = load_our_model("/content/gdrive/MyDrive/ATS/stage2_Model")
num_params = model.num_parameters()
print("Number of parameters in T5-small :", num_params)

test_dataset = selected_test_examples
rouge_scoresa = calculate_rouge_scores(model, tokenizer, test_dataset)
rouge_dff = rouge_scores_to_dataframe(rouge_scoresa)

# Display the DataFrame
print("Fine-Tuned ROUGE Scores:\n", rouge_dff)

modelp, tokenizerp = load_t5_model("t5-small")
rouge_scoresp = calculate_rouge_scores(modelp, tokenizerp, test_dataset)
rouge_dfn = rouge_scores_to_dataframe(rouge_scoresp)

# Display the DataFrame
print("Normal ROUGE Scores:\n", rouge_dfn)

#Stage3
# Select consecutive examples from the training dataset.
start_index_train = 20000  # Adjust the starting index as needed
selected_train_examples = select_consecutive_examples(train_dataset, start_index_train, 5000)

# Select consecutive examples from the validation dataset.
start_index_valid = 2000  # Adjust the starting index as needed
selected_valid_examples = select_consecutive_examples(validation_dataset, start_index_valid, 500)

# Select consecutive examples from the test dataset.
start_index_test = 2000  # Adjust the starting index as needed
selected_test_examples = select_consecutive_examples(test_dataset, start_index_test, 500)

preprocessed_train_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_train_examples]
preprocessed_validation_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_valid_examples]
preprocessed_test_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_test_examples]

print(f"\nPreprocessed")
print(f"Training dataset size: {len(preprocessed_train_data)}")
print(f"Validation dataset size: {len(preprocessed_validation_data)}")
print(f"Test dataset size: {len(preprocessed_test_data)}")

# Save the preprocessed training data.
save_preprocessed_data_to_txt(preprocessed_train_data, "stage3_train_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_validation_data, "stage3_validation_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_test_data, "stage3_test_data.json")

# Fine-tune the model stage3
fine_tune_T5("/content/drive/MyDrive/ATS/stage2_Model", "/content/stage3_train_data.json","/content/stage3_validation_data.json","/content/stage3_test_data.json", "stage3_Model")

print("STAGE-3 ROUGE Scores:\n")

model, tokenizer = load_our_model("/content/drive/MyDrive/ATS/stage3_Model")
num_params = model.num_parameters()
print("Number of parameters in T5-small :", num_params)

test_dataset = selected_test_examples
rouge_scoresa = calculate_rouge_scores(model, tokenizer, test_dataset)
rouge_dff = rouge_scores_to_dataframe(rouge_scoresa)

# Display the DataFrame
print("Fine-Tuned ROUGE Scores:\n", rouge_dff)

modelp, tokenizerp = load_t5_model("t5-small")
rouge_scoresp = calculate_rouge_scores(modelp, tokenizerp, test_dataset)
rouge_dfn = rouge_scores_to_dataframe(rouge_scoresp)

# Display the DataFrame
print("Normal ROUGE Scores:\n", rouge_dfn)

#Stage4
# Select consecutive examples from the training dataset.
start_index_train = 3000  # Adjust the starting index as needed
selected_train_examples = select_consecutive_examples(train_dataset, start_index_train, 1000)

# Select consecutive examples from the validation dataset.
start_index_valid = 300  # Adjust the starting index as needed
selected_valid_examples = select_consecutive_examples(validation_dataset, start_index_valid, 100)

# Select consecutive examples from the test dataset.
start_index_test = 300  # Adjust the starting index as needed
selected_test_examples = select_consecutive_examples(test_dataset, start_index_test, 100)

preprocessed_train_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_train_examples]
preprocessed_validation_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_valid_examples]
preprocessed_test_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_test_examples]

print(f"\nPreprocessed")
print(f"Training dataset size: {len(preprocessed_train_data)}")
print(f"Validation dataset size: {len(preprocessed_validation_data)}")
print(f"Test dataset size: {len(preprocessed_test_data)}")

# Save the preprocessed training data.
save_preprocessed_data_to_txt(preprocessed_train_data, "stage4_train_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_validation_data, "stage4_validation_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_test_data, "stage4_test_data.json")

# Fine-tune the model stage4
fine_tune_T5("stage3_Model", "/content/stage4_train_data.json","/content/stage4_validation_data.json","/content/stage4_test_data.json", "stage4_Model")

#Stage5
# Select consecutive examples from the training dataset.
start_index_train = 4000  # Adjust the starting index as needed
selected_train_examples = select_consecutive_examples(train_dataset, start_index_train, 1000)

# Select consecutive examples from the validation dataset.
start_index_valid = 400  # Adjust the starting index as needed
selected_valid_examples = select_consecutive_examples(validation_dataset, start_index_valid, 100)

# Select consecutive examples from the test dataset.
start_index_test = 400  # Adjust the starting index as needed
selected_test_examples = select_consecutive_examples(test_dataset, start_index_test, 100)

preprocessed_train_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_train_examples]
preprocessed_validation_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_valid_examples]
preprocessed_test_data = [preprocess_example(example["article"], example["highlights"]) for example in selected_test_examples]

print(f"\nPreprocessed")
print(f"Training dataset size: {len(preprocessed_train_data)}")
print(f"Validation dataset size: {len(preprocessed_validation_data)}")
print(f"Test dataset size: {len(preprocessed_test_data)}")

# Save the preprocessed training data.
save_preprocessed_data_to_txt(preprocessed_train_data, "stage5_train_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_validation_data, "stage5_validation_data.json")

# Save the preprocessed validation data.
save_preprocessed_data_to_txt(preprocessed_test_data, "stage5_test_data.json")

# Fine-tune the model stage5
fine_tune_T5("stage4_Model", "/content/stage5_train_data.json","/content/stage5_validation_data.json","/content/stage5_test_data.json", "stage5_Model")

"""**Fine-Tuning the Model**

**Functions for getting Insights**
"""

import matplotlib.pyplot as plt

def plot_training_graph(train_losses, val_losses):
    # Extract values from TrainOutput object
    train_loss = train_losses.training_loss
    val_loss = val_losses['eval_loss']

    # Plot Training and Validation Loss
    plt.plot(train_loss, label='Training Loss')
    plt.plot(val_loss, label='Validation Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()
    plt.show()

# # Print information about the losses
# print("Training Losses:", training_losses)
# print("Validation Losses:", validation_losses)

# Plot Training and Validation Graph
# plot_training_graph(training_losses, validation_losses)

"""**Loading Fine-Tuned Model**"""

model, tokenizer = load_our_model("/content/stage4_Model")
num_params = model.num_parameters()
print("Number of parameters in T5-small :", num_params)

"""**Tensor-Board**"""

# Commented out IPython magic to ensure Python compatibility.
# %load_ext tensorboard
# %tensorboard --logdir ./logs

"""**Sample Test of Model**"""

# Define reference and generated summaries for ROUGE calculation
reference_summaries = '''Harry Potter star Daniel Radcliffe gets £20M fortune as he turns 18 Monday . Young actor says he has no plans to fritter his cash away . Radcliffe's earnings from first five Potter films have been held in trust fund'''
# Input text for summarization
input_text = '''LONDON, England (Reuters) -- Harry Potter star Daniel Radcliffe gains access to a reported £20 million ($41.1 million) fortune as he turns 18 on Monday, but he insists the money won't cast a spell on him. Daniel Radcliffe as Harry Potter in "Harry Potter and the Order of the Phoenix" To the disappointment of gossip columnists around the world, the young actor says he has no plans to fritter his cash away on fast cars, drink and celebrity parties. "I don't plan to be one of those people who, as soon as they turn 18, suddenly buy themselves a massive sports car collection or something similar," he told an Australian interviewer earlier this month. "I don't think I'll be particularly extravagant. "The things I like buying are things that cost about 10 pounds -- books and CDs and DVDs." At 18, Radcliffe will be able to gamble in a casino, buy a drink in a pub or see the horror film "Hostel: Part II," currently six places below his number one movie on the UK box office chart. Details of how he'll mark his landmark birthday are under wraps. His agent and publicist had no comment on his plans. "I'll definitely have some sort of party," he said in an interview. "Hopefully none of you will be reading about it." Radcliffe's earnings from the first five Potter films have been held in a trust fund which he has not been able to touch. Despite his growing fame and riches, the actor says he is keeping his feet firmly on the ground. "People are always looking to say 'kid star goes off the rails,'" he told reporters last month. "But I try very hard not to go that way because it would be too easy for them." His latest outing as the boy wizard in "Harry Potter and the Order of the Phoenix" is breaking records on both sides of the Atlantic and he will reprise the role in the last two films. Watch I-Reporter give her review of Potter's latest » . There is life beyond Potter, however. The Londoner has filmed a TV movie called "My Boy Jack," about author Rudyard Kipling and his son, due for release later this year. He will also appear in "December Boys," an Australian film about four boys who escape an orphanage. Earlier this year, he made his stage debut playing a tortured teenager in Peter Shaffer's "Equus." Meanwhile, he is braced for even closer media scrutiny now that he's legally an adult: "I just think I'm going to be more sort of fair game," he told Reuters. E-mail to a friend . Copyright 2007 Reuters. All rights reserved.This material may not be published, broadcast, rewritten, or redistributed.'''
generated_summary = generate_summary(model, tokenizer, input_text)
# print(model)
# print(tokenizer)

# Print or use the generated summary
print("Generated Abstractive Summary:", generated_summary)
print(f"Input Text length : {len(input_text)}")
print(f"Generated Summary length : {len(generated_summary)}")
print(f"Reference Summary length : {len(reference_summaries)}")

"""**Rouge-Score**"""

# Example usage
# Access the test split
test_dataset = selected_test_examples
rouge_scoresa = calculate_rouge_scores(model, tokenizer, test_dataset)
rouge_dff = rouge_scores_to_dataframe(rouge_scoresa)

# Display the DataFrame
print("Fine-Tuned ROUGE Scores:\n", rouge_dff)

modelp, tokenizerp = load_t5_model("t5-small")
rouge_scoresp = calculate_rouge_scores(modelp, tokenizerp, test_dataset)
rouge_dfn = rouge_scores_to_dataframe(rouge_scoresp)

# Display the DataFrame
print("Normal ROUGE Scores:\n", rouge_dfn)

# Launch Gradio interface for abstractive summarization
gradio_interface(model, tokenizer)
