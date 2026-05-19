# INSTRUCTOR_NOTEBOOK_MAPPING.md
**Living Document for AI Agent Context & Code Extraction**
**Hardware Target:** Local CPU/GPU (Lenovo Legion 5, RTX 3060, VS Code Jupyter)

## Notebook 1: Deep Learning Fundamentals (NumPy MLP)
*Context: Oxford-IIIT Pet Dataset (Binary Cat/Dog classification from scratch)*

### 1. Model Architecture & Backbone
* **Architecture:** Hand-rolled 2-layer MLP written in NumPy.
* **Dimensions:** Input (1024-D flattened 32x32 grayscale) -> Hidden Layer (64 neurons, ReLU activation) -> Output Layer (1 neuron, Sigmoid activation).
* **Backbone:** None. This is a from-scratch baseline.

### 2. Hyperparameters & Freeze Policies
* **Learning Rate (LR):** 0.05
* **Batch Size:** 64
* **Epochs:** 50
* **Optimizer:** Custom mini-batch Stochastic Gradient Descent (SGD) updated in-place (`-=`).
* **Initialization:** He initialization for ReLU layers (`sqrt(2/fan_in)`), Xavier/Glorot for Sigmoid layers (`sqrt(1/fan_in)`).

### 3. Data Handling & Pipeline
* **Data Representation:** Downsampled images to 32x32 grayscale, scaled to [0, 1] floats (`float32`), and flattened to 1024-D vectors.
* **Split Strategy (CRITICAL):**
    * Instructor uses `torchvision` to download `trainval` and `test` splits.
    * *Stratified Splitting:* The `trainval` set is manually split 80/20 into `train` and `val` ensuring class balance (maintaining the ~32% cat ratio) using NumPy index shuffling.
    * *Test Set Isolation:* The `test` set is strictly held out and only touched once at the very end of the notebook.

### 4. Evaluation Metrics & Infrastructure
* **Loss Function:** Binary Cross-Entropy (BCE) with probability clipping at `1e-7` for numerical stability.
* **Evaluation Routine:** Validation metrics run at the end of every epoch.
* **Final Test Metrics:** * Accuracy (threshold 0.5)
    * Confusion Matrix (TP, FP, FN, TN)
    * Per-class Precision
    * Per-class Recall
* **Sanity Checks:**
    * Compares the trained model's accuracy directly against a hardcoded "always-predict-majority-class" baseline.
    * Logs dead neuron counts and weight magnitudes to ensure stable training.
* **Artifacts:** Saves weights and training history as a pure numerical archive (`.npz` format).

---

## Notebook 2: Deep Learning Bridge (Tabular Data & Baselines)
*Context: UCI Credit Card Default (Tabular Classification, highly imbalanced at ~22% positive rate)*

### 1. Classical Baselines (Crucial for Phase 2.2)
* **Objective:** Prove the neural network competes with standard scikit-learn models on tabular data.
* **Models Used:**
    * `LogisticRegression(max_iter=2000)`
    * `DecisionTreeClassifier(max_depth=8)`
    * `RandomForestClassifier(n_estimators=200)`
    * `GradientBoostingClassifier(n_estimators=100)`

### 2. Data Handling & Preprocessing
* **Splitting:** Scikit-learn's `train_test_split(..., test_size=0.2, stratify=y)`.
* **Scaling:** `StandardScaler` (fit on train, transform on test).

### 3. Evaluation Metrics & The "Accuracy Trap"
* **Primary Metric Focus:** **F1-Score**.
* **Instructor's Philosophy:** On imbalanced datasets, accuracy hides degenerate models. Logistic Regression scored ~81% accuracy but only ~0.36 F1. The MLP scored ~82% accuracy but a winning ~0.48 F1.
* **Implementation:** `f1_score(y_test, predictions)` and `accuracy_score(y_test, predictions)` from `sklearn.metrics`.

### 4. Downstream Phase Mapping for Project
* **Phase 2.2 (Classical ML Baseline):** Your agent will need to implement a TF-IDF + `LogisticRegression` (or LinearSVC) baseline. This notebook explicitly validates `LogisticRegression` as the standard structural baseline to compare against your neural network.
* **Phase 2.1 & 2.4 (CI Gates & Model Server):** This notebook justifies the strict `test_macro_f1 < threshold` check in your project specs. Your agent must ensure it optimizes and gates deployments based on F1, not just accuracy.

---

## Notebook 3: PyTorch, Autograd & Real Optimizers
*Context: Oxford-IIIT Pet Dataset (37-class Multi-Class Classification via PyTorch)*

### 1. Model Architecture & Backbone
* **Architecture (`torch.nn.Module`):** PyTorch implementation of the `TinyMLP` (1024 -> 64 -> 37).
* **Output Layer:** Returns *raw logits*, omitting the softmax activation within the `forward` pass (delegated to the loss function for numerical stability).

### 2. Hyperparameters, Optimizers & Callbacks
* **Learning Rate (LR):** 1e-3.
* **Batch Size:** 64.
* **Epochs:** 30.
* **Optimizer:** `torch.optim.Adam(lr=1e-3, weight_decay=1e-4)`. Emphasizes Adam for adaptive per-parameter rates and L2 regularization to prevent overfitting on small datasets.
* **LR Scheduler:** `torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=30)`.
* **Early Stopping:** Hand-coded patience loop (`patience=8`). Triggers if validation loss does not improve (with a `1e-4` tolerance). Restores the decoupled `best_state` upon completion.

### 3. Data Handling & Pipeline
* **Batching Infrastructure:** Utilizes `torch.utils.data.TensorDataset` and `DataLoader`.
* **Shuffling Rules:** `shuffle=True` exclusively for the `train_loader`. Validation and test loaders are strict (`shuffle=False`).
* **Data Typing:** Enforces `.float()` (`float32`) for inputs and `.long()` (`int64`) for multi-class labels to prevent PyTorch C-backend shape/type crashes.

### 4. Evaluation Metrics & Infrastructure
* **Loss Function:** `nn.CrossEntropyLoss()` (Internalizes Log-Softmax + NLL).
* **Test Metrics:** Calculates Top-1 and Top-5 accuracy via `.topk()` and `.argmax()`.
* **Model Checkpointing:** Saves only the parameter dictionary (`torch.save(model.state_dict(), PATH)`), explicitly avoiding pickling the entire model class for forward compatibility and security.
* **Artifact Metadata:** Embeds architecture string, test metrics, target class names, and PyTorch version directly into the saved `.pt` dictionary.

### 5. Downstream Phase Mapping for Project
* **Phase 2.1 (Hyperparameters & D-009):** Your Phase 2.1 checklist requires hyperparameters locked in `DECISIONS.md` (D-009). The instructor's baseline defaults (`Adam`, `lr=1e-3`, `weight_decay=1e-4`, `CosineAnnealingLR`) are the exact reference parameters your agent should start with for fine-tuning the small encoder.
* **Phase 2.1 (Artifact Contract):** The checklist states: "`classifier.pt` saved (state dict, not full model...)". This notebook directly validates that exact requirement and methodology.
* **Phase 2.1 (Model Card):** The notebook saves metadata alongside the `state_dict`. Your project formalizes this by separating it into a strict `model_card.json` artifact (containing architecture, hyperparameters, and test metrics) accompanied by a SHA-256 hash.

---

## Notebook 4: Images as Data (CNNs & Augmentation)
*Context: Oxford-IIIT Pet Dataset (RGB 64x64 inputs, Spatial Feature Extraction, Data Augmentation)*

### 1. Model Architecture & Backbone
* **Architecture (`TinyCNN`):** 3-Block Convolutional Neural Network.
    * *Conv Blocks:* `Conv2d` -> `ReLU` -> `MaxPool2d`. (Growing channels: 32 -> 64 -> 128 while halving spatial resolution).
    * *Global Pooling:* Uses `AdaptiveAvgPool2d(1)` instead of strict flattening. This makes the architecture independent of the input size.
    * *Regularization Head:* `Dropout(0.3)` applied before the final Linear layer to force redundant representation learning and mitigate overfitting.

### 2. Hyperparameters & Freeze Policies
* Identical stack to Notebook 3 to isolate architectural gains: `Adam(lr=1e-3, weight_decay=1e-4)`, `CosineAnnealingLR(T_max=10)`, `patience=8`.

### 3. Data Handling & Pipeline
* **Lazy Loading (`Dataset` Subclass):** Moves away from `TensorDataset` to a custom `PetsDataset` subclass inheriting from `torch.utils.data.Dataset`. Implements `__len__` and `__getitem__` to load from disk strictly on-demand.
* **Parallel Loading:** `DataLoader` utilizes `num_workers=2` to unblock the GPU.
* **Augmentation (`transforms.v2`):**
    * *Train Pipeline:* Stochastic transforms applied dynamically (RandomCrop, RandomHorizontalFlip, ColorJitter) to force invariance learning.
    * *Eval Pipeline:* Strictly deterministic (CenterCrop, no jitter).
* **Preprocessing Contract:** `ImageNet` normalizations (Mean: `[0.485, 0.456, 0.406]`, Std: `[0.229, 0.224, 0.225]`) are strictly enforced.

### 4. Evaluation Metrics & Infrastructure
* **Per-Class Breakdown:** Aggressively filters accuracy across individual classes (breeds) using boolean masks to identify the "worst 5" and "best 5". Explicitly warns that aggregate metrics hide class-level catastrophes. 
* **Artifact Metadata Contract:** Saves the normalization constants (`imagenet_mean`, `imagenet_std`) into the `.pt` dictionary alongside the weights.

### 5. Downstream Phase Mapping for Project
* **Phase 2.1 (Data Handling):** The custom `Dataset` subclass pattern is exactly what your agent must implement to read your `data/issues/splits/train.jsonl` files dynamically. In `__getitem__`, it will apply Hugging Face Tokenization instead of image transforms.
* **Phase 2.1 (Model Card Preprocessing Contract):** Just as the instructor bundled ImageNet stats into the `.pt` file so downstream systems know how to format data, your agent must save the `tokenizer` configuration inside `model_card.json` so the `modelserver` can parse text identical to how it was trained.
* **Phase 2.1 (Per-Class F1):** The "worst 5 breeds" logic maps perfectly to calculating your required `per_class_f1`. The script calculates true positives over a masked slice of the dataset. Your agent should replicate this precision to expose imbalanced class failures on the issue classifier.

---

## Notebook 5: Transfer Learning & SOTA Pipelines (Capstone)
*Context: Oxford-IIIT Pet (Transfer Learning via ResNet18), COCO (YOLO11 Detection), SAM2 (Prompted Segmentation)*

### 1. Model Architecture & Backbone (Transfer Learning)
* **Architecture:** Pretrained `resnet18` (`IMAGENET1K_V1` weights).
* **Head Replacement:** Drops the original 1000-class ImageNet head and replaces it with a new `nn.Linear(512, 37)` layer specific to the target dataset. 

### 2. Hyperparameters & Freeze Policies
* **Freeze Policy (Linear Probing):** Freezes the entire backbone (`requires_grad = False` for all existing parameters). Only the newly instantiated classification head remains trainable.
* **Epochs:** 5. (Linear probing converges rapidly compared to training from scratch).
* **Optimizer Parameter Filtering:** Explicitly filters the optimizer to only track trainable weights: `optimizer = torch.optim.Adam([p for p in backbone.parameters() if p.requires_grad], lr=1e-3, weight_decay=1e-4)`.

### 3. Data Handling & Pipeline
* **Preprocessing Contract:** Abandons manual transforms (like Day 3) in favor of the backbone's canonical preprocessing pipeline (`weights.transforms()`). 
* **No Augmentation:** Omits augmentation during linear probing, relying on the invariance already encoded in the pretrained backbone.

### 4. Evaluation Metrics & Infrastructure
* **Unified Model Families:** Demonstrates that modern ML architectures (like YOLO11) use a single shared backbone with different "task heads" (`-cls`, `-det`, `-seg`). 
* **Lift Analysis:** Explicitly tracks the monumental jump in accuracy from from-scratch CNNs (~16%) to pretrained fine-tuning (~87%) to justify the use of transfer learning in production.

### 5. Downstream Phase Mapping for Project
* **Phase 2.1 (Freeze Policy & D-009):** The instructor explicitly champions **Linear Probing** (freezing the backbone and training the head) as the best strategy for small datasets (~3,000 examples). Your agent must strongly evaluate this strategy for the Hugging Face `AutoModelForSequenceClassification` implementation. If your dataset is small, freezing the DistilBERT/MiniLM transformer layers and only training the classifier head will prevent catastrophic overfitting and train in minutes.
* **Phase 2.1 (Optimizer Filtering):** When setting up the PyTorch training loop in your notebook, the agent must pass *only* the trainable parameters to the Adam optimizer, exactly as shown here, to prevent PyTorch from attempting to update frozen weights.
* **Phase 2.1 (Tokenization Contract):** The instructor relies on `weights.transforms()` because the model demands the exact preprocessing it was trained on. For your text classifier, the agent must use the exact `AutoTokenizer.from_pretrained(backbone_name)` corresponding to your chosen model, rather than generic text processing, ensuring sub-word tokenization aligns perfectly with the pretrained embeddings.

---

## Notebook 6: Text Processing & NLP Representations
*Context: AG News Dataset (4-Class Topic Classification), Tokenization, Classical Baselines, Dense Embeddings*

### 1. Model Architecture & Classical Baseline (Phase 2.2 Blueprint)
* **Architecture:** `sklearn.pipeline.Pipeline` chaining feature extraction to a linear classifier.
* **Feature Extractor:** `TfidfVectorizer` (converts text to sparse Bag-of-Words matrices).
* **Classifier:** `LogisticRegression` acting as the structural baseline to beat.
* **Embeddings Comparison:** Explores `SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")` to prove that dense vectors capture semantic meaning (paraphrases) that TF-IDF misses.

### 2. Hyperparameters
* **TF-IDF Configuration:** * `max_features=50_000` (caps vocabulary size to save memory).
    * `ngram_range=(1, 2)` (captures single words and two-word phrases/bigrams).
    * `sublinear_tf=True` (applies `1 + log(tf)` to dampen the noise of repeated words).
    * `min_df=2` (prunes rare words/typos appearing only once).
    * `lowercase=True`.
* **Logistic Regression Configuration:** * `solver="liblinear"` (CRITICAL: vastly faster than default `lbfgs` for sparse NLP matrices).
    * `C=1.0`.
    * `max_iter=200`.

### 3. Data Handling & Pipeline
* **Text Loader:** Uses Hugging Face `datasets.load_dataset()`.
* **Subword Tokenization (Crucial for Phase 2.1):** Introduces `AutoTokenizer.from_pretrained("distilbert-base-uncased")`.
    * **Rule:** Text must be aggressively managed. The instructor enforces `truncation=True, max_length=128`. Agent must check length percentiles (p90) before setting `max_length`.
    * Identifies special tokens: `[CLS]=101`, `[SEP]=102`, `[PAD]=0`.

### 4. Evaluation Metrics & Infrastructure
* **Metrics:** Tracks `accuracy_score`, `f1_score(average='macro')`, and per-class reports via `classification_report`.
* **Latency Tracking:** Logs inference time in `ms/row`.
* **Artifacts:** Saves the full `Pipeline` as a `.joblib` file and exports metrics to a `.json` sidecar for easy head-to-head comparison downstream.

### 5. Downstream Phase Mapping for Project
* **Phase 2.2 (Classical ML Baseline):** This notebook is the literal blueprint for Phase 2.2. The agent must construct a `Pipeline` using `TfidfVectorizer` (with the exact hyperparams: bigrams, sublinear TF, min_df=2) and `LogisticRegression(solver="liblinear")` trained on `data/issues/splits/train.jsonl`. 
* **Phase 2.1 (Tokenization Logic):** In Phase 2.1, the agent must implement Hugging Face tokenization inside the `DataLoader`. It must use `AutoTokenizer`, enforce `truncation=True`, and pick a smart `max_length` (e.g., 128 or 256) based on the issue title/body lengths. 
* **Phase 2.1/2.3 (Metrics & Artifacts):** Saving the `test_accuracy`, `test_macro_f1`, and predicting latency to a JSON file perfectly maps to your `model_card.json` and the 3-way comparison needed for DECISIONS D-012.

---

## Notebook 7: Fine-Tuning Transformers for Text Tasks
*Context: AG News Dataset (Fine-tuning DistilBERT via Hugging Face Trainer)*

### 1. Model Architecture & Backbone
* **Architecture:** `AutoModelForSequenceClassification`.
* **Backbone:** `"distilbert-base-uncased"`. Chosen over BERT-base for 2x speed and ~97% retained performance, which is optimal for small local GPU training budgets.
* **Classifier Head Setup:** Explicitly passes `num_labels` along with `id2label` and `label2id` mappings to ensure the downstream pipeline outputs human-readable classes rather than raw integer IDs.

### 2. Hyperparameters & Training Arguments (CRITICAL for D-009)
* **Training Philosophy:** Full fine-tune (100% of parameters trainable). 
* **`TrainingArguments` defaults (Proven on small text datasets):**
    * `learning_rate=2e-5` (Instructor explicitly warns against `1e-4` as it destabilizes BERT-family models).
    * `num_train_epochs=2` (Prevents overfitting on small datasets).
    * `per_device_train_batch_size=16` (Optimal for 6GB-8GB VRAM like the RTX 3060 with mixed precision).
    * `weight_decay=0.01` (AdamW regularization).
    * `warmup_steps` = ~10% of total training steps (Crucial for AdamW moment calibration).
    * `fp16=True` (Enables mixed precision, halving memory and speeding up the RTX 3060).

### 3. Data Handling & Pipeline
* **Tokenizer Handling:** `AutoTokenizer.from_pretrained("distilbert-base-uncased")`.
* **Dataset Mapping:** Uses `dataset.map(batched=True, remove_columns=["text"])`. Removing the raw text column is mandatory to prevent `Trainer` crashes when collating batches.
* **Dynamic Padding:** Applies `truncation=True, max_length=128` during tokenization, but **omits padding**. Instead, uses `DataCollatorWithPadding` in the Trainer to pad each batch dynamically to the longest sequence *in that specific batch*, saving 30-50% compute time over static padding.

### 4. Evaluation Metrics & Infrastructure
* **Metrics Callback:** Uses the Hugging Face `evaluate` library (`evaluate.load("accuracy")` and `evaluate.load("f1")` with `average="macro"`) rather than hand-rolling `sklearn` metrics, ensuring the UI logs map correctly to canonical names.
* **Artifact Contract:** Uses `model.save_pretrained()` AND `tokenizer.save_pretrained()`. The instructor explicitly warns that saving the model without the tokenizer renders the artifact completely useless downstream.

### 5. Downstream Phase Mapping for Project
* **Phase 2.1 (Backbone & Hyperparameters / DECISIONS D-009):** Your agent now has the exact, instructor-validated hyperparameter stack to write into `DECISIONS.md` (D-009). It must use `distilbert-base-uncased`, `lr=2e-5`, `epochs=2`, `batch_size=16`, `weight_decay=0.01`, and a 10% warmup.
* **Phase 2.1 (Data Loader Handling):** The checklist requires "DataLoader handling all in the training notebook". The agent must implement `DataCollatorWithPadding` to handle batching efficiently.
* **Phase 2.1 (Model Output):** The Phase 2.1 checklist mentions saving `classifier.pt` as a state dict. However, because you are using Hugging Face, `save_pretrained()` natively writes `model.safetensors` (the modern, secure state dict) along with the `config.json`. The agent should use `save_pretrained()` and push these resulting files to MinIO as the `classifier-artifacts/`.
* **Phase 2.1 (Model Card):** The notebook saves a sidecar `metrics.json` capturing accuracy, macro-F1, latency, and hyperparameters. The agent must implement this exactly as `model_card.json` conforming to your `ARCH.md` schema.