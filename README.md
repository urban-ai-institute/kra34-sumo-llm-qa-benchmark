# NetTrafficQA

LLM이 SUMO 시뮬레이션 파일을 얼마나 잘 읽고 추론하는지 측정하는 벤치마크.
세 가지 scaffolding 조건(파일을 LLM에게 어떻게 보여줄 것인가)을 비교한다.

## 구조

```
NetTrafficQA_/
├── data/
│   ├── network/                  # SUMO 네트워크 (.net.xml, _adjacency.json, _tls.add.xml)
│   ├── trips/                    # 차량 수요 (.rou.xml)
│   ├── output/                   # 시뮬레이션 결과 (tripinfo.xml, fcd.xml)
│   └── preprocessed/             # JSON condition 입력 (.jsonl, build_jsonl.py 산출물)
├── scripts/
│   ├── utils.py                  # 공통 유틸 (파일 경로, Anthropic 클라이언트)
│   ├── build_jsonl.py            # SUMO XML → JSONL 변환 (data/preprocessed/ 빌드)
│   └── methods/
│       ├── xml_view.py           # SUMO XML condition
│       ├── json_view.py          # JSON condition
│       └── tool_use.py           # Tool-Use condition
├── QAdataset/
│   ├── questions/                # 질문 + 정답 CSV  {network}_{type}.csv (81 files)
│   └── results/                  # 실험 결과 CSV   {condition}_{network}_{type}.csv
├── run_simulation.py             # SUMO 시뮬레이션 (once-only, deterministic seed=42)
├── run_preprocess.py             # net.xml → adjacency.json (once-only)
├── generate_qa.py                # 32-type 질문+정답 매트릭스 생성
├── run_experiment.py             # LLM 응답 수집
├── evaluate.py                   # 정답 채점 및 정확도 집계
├── run.sh                        # 전체 파이프라인 실행
└── README.md
```

## Scaffolding conditions

세 가지 방식으로 SUMO 파일을 LLM에게 노출하고 정확도를 비교한다.

| Condition | 입력 | 설명 |
|---|---|---|
| **SUMO XML** | `.net.xml`, `.rou.xml`, `tripinfo.xml`, `fcd.xml`, `_tls.add.xml`의 원본 내용을 prompt에 삽입 | LLM이 XML을 직접 읽고 답함. TrafficNetQA 등 선행 연구가 사용한 baseline. |
| **JSON** | 같은 파일을 JSONL(한 줄당 한 객체)로 변환해서 prompt에 삽입. `net.xml`에는 *미리 계산된 인접 리스트* (outgoing_edges, neighbor_junctions, next_edges) 컬럼이 추가됨 | XML의 nested 구조를 평면 JSONL로 바꾸고, 그래프 추론을 돕는 인접 정보를 명시적으로 포함. 옛 `adj` baseline의 그래프 정보 주입을 흡수한 형태. |
| **Tool-Use** | 파일 *경로*와 `run_python` 도구만 제공. LLM이 Python 코드를 직접 작성해서 실행 | 옛 `codegen` baseline에 해당. persistent Python session, 10-turn budget, 60초 timeout. |

## 데이터셋 (QAdataset)

`QAdataset/questions/`에 `{network}_{type}.csv` 형태로 평면 저장. 한 CSV에 5개 질문 (sample_id 0~4).

**총 96 파일** = 3 networks × 32 types. 각 행에 `question`과 `ground_truth`가 함께 포함되어 있다.

| Category | # types | 예시 |
|---|---|---|
| Retrieval | 12 | `both_junctions`, `num_lanes`, `vehicle_depart_edge`, `vehicle_route`, `vehicles_with_same_origin`, `tls_phase_count`, `tls_longest_green_phase` |
| Reasoning (single-file) | 10 | `shortest_path_full`, `vehicles_passing_edge`, `vehicle_max_speed`, `tls_total_cycle_time` |
| Multi-step reasoning (multiple files) | 10 | `edge_removal_route_count`, `worst_congestion_od`, `tls_delay` |

각 type은 *Retrieval* (단일 파일, 단일 필드 조회), *Reasoning* (단일 파일, 그래프 탐색·필터링·집계 등 계산 필요), *Multi-step reasoning* (복수 파일 통합 + 다단계 계산)으로 분류된다. 자세한 매트릭스는 `paper_writing/NetTrafficQA_CIKM/Tables/question_types.tex` 참고.

## 실행

API 키 (`claude_api.txt` 또는 `$ANTHROPIC_API_KEY`) 와 `$SUMO_HOME` 이 설정되어 있어야 한다.

### 전체 파이프라인

```bash
bash run.sh
```

기본 흐름:
1. `run_simulation.py` — SUMO 시뮬 (한 번만; 결과는 repo에 포함되어 있어 보통 skip)
2. `scripts/build_jsonl.py` — JSON condition용 JSONL 빌드
3. `generate_qa.py` — 32-type 질문+정답 매트릭스 생성
4. `run_experiment.py --all` — 3 conditions × 3 networks × 32 types × 5 samples = 1,440 calls
5. `evaluate.py` — 결과 채점

### 부분 실행

```bash
# 단일 condition만
python run_experiment.py --all --condition tool

# 단일 network만
python run_experiment.py --all --network grid_8x8

# 단일 question type만 (모든 network/condition)
python run_experiment.py --type both_junctions
```

이미 채워진 결과 CSV는 자동 skip된다. `--force`로 덮어쓰기 가능.

### 평가

```bash
python evaluate.py
```

전체 결과를 읽고 `{condition}_{network}_{type}_evaluated.csv`를 생성. (condition × category × network) 단위로 정확도를 출력한다.
