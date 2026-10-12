"""
파인튜닝 스크립트 (Google Colab용)

사용법
1) colab.research.google.com → 새 노트북 → 런타임 > 런타임 유형 변경 > T4 GPU
2) 왼쪽 폴더 아이콘에 train.jsonl 파일 업로드
3) 아래 코드를 칸(셀) 단위로 나눠 붙여넣고 위에서부터 실행
   ("# ===== 셀 N =====" 표시가 칸 구분입니다)

※ 라이브러리 버전이 자주 바뀌어서, 오류가 나면 Unsloth 공식 노트북
   (docs.unsloth.ai 의 Colab 예제)의 최신 코드와 비교해 보세요.
"""

# ===== 셀 1: 설치 (처음 한 번, 몇 분 걸림) =====
# !pip install unsloth

# ===== 셀 2: 모델 불러오기 =====
from unsloth import FastLanguageModel

MODEL = "unsloth/Qwen2.5-7B-Instruct"   # 한국어가 비교적 좋은 모델. T4(무료)에서도 4bit로 가능

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL,
    max_seq_length=2048,
    load_in_4bit=True,          # 메모리 절약
)

# LoRA: 모델 전체가 아니라 작은 보조 층만 학습 (가볍고 빠름)
model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    lora_alpha=16,
    lora_dropout=0,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"],
    use_gradient_checkpointing="unsloth",
    random_state=3407,
)

# ===== 셀 3: 학습 데이터 불러오기 =====
from datasets import load_dataset
from unsloth.chat_templates import get_chat_template

tokenizer = get_chat_template(tokenizer, chat_template="qwen-2.5")

dataset = load_dataset("json", data_files="train.jsonl", split="train")

def to_text(example):
    # messages(시스템/질문/답변)를 모델이 읽는 한 덩어리 글로 바꿈
    return {"text": tokenizer.apply_chat_template(
        example["messages"], tokenize=False, add_generation_prompt=False)}

dataset = dataset.map(to_text)
print(f"학습 데이터 {len(dataset)}개")
print(dataset[0]["text"][:500])   # 눈으로 한 번 확인

# ===== 셀 4: 학습 (데이터 300개 기준 10~30분) =====
from trl import SFTTrainer, SFTConfig

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    args=SFTConfig(
        dataset_text_field="text",
        max_seq_length=2048,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,          # 데이터를 3바퀴 공부. 너무 크면 외워버려서 2~3 추천
        learning_rate=2e-4,
        logging_steps=10,            # loss(오차)가 점점 줄어들면 잘 되는 중
        optim="adamw_8bit",
        output_dir="outputs",
        report_to="none",
    ),
)
trainer.train()

# ===== 셀 5: 시험해보기 =====
FastLanguageModel.for_inference(model)
messages = [{"role": "user", "content": "블로그 자동화로 만들 수 있는 수익 아이디어 3개만 알려줘"}]
inputs = tokenizer.apply_chat_template(
    messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
).to("cuda")
out = model.generate(input_ids=inputs, max_new_tokens=300)
print(tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True))

# ===== 셀 6: Ollama용 파일(GGUF)로 내보내기 =====
model.save_pretrained_gguf("my_model", tokenizer, quantization_method="q4_k_m")
# 왼쪽 폴더에서 .gguf 파일을 찾아 내 PC로 다운로드하세요.
#
# ── 내 PC에서 (Ollama에 등록) ──
# 1) 같은 폴더에 'Modelfile' 이라는 이름의 파일을 만들고 한 줄만 적기:
#        FROM ./다운받은파일이름.gguf
# 2) 터미널에서:
#        ollama create my-idea-model -f Modelfile
# 3) config.py 의 CHAT_MODEL = "my-idea-model" 로 바꾸면 끝
