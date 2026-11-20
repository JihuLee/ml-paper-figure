# ml-paper-figure

NeurIPS · ICML · ICLR · CVPR 등 ML/AI 학회 논문에 바로 넣을 수 있는 **Figure 1**(프레임워크 개요, 모델 아키텍처,
파이프라인 다이어그램)을 만드는 재사용 가능한 Agent Skill입니다. 에이전트가 바로 SVG를 그리지 않고
**Plan → Draft → Render & Critique(최대 3회) → Export** 4단계를 거치도록 강제합니다. 결과물은
자급자족형 `.svg`, LaTeX용 벡터 `.pdf`, 발표·미리보기용 고해상도 `.png`입니다.

![example](examples/uncertainty-aware/figure1_uam.png)

*위 그림은 스킬 검증 실행 결과입니다(Frozen Encoder → 제안 모듈 UAM → Decoder + 점선 손실 경로).
과정은 [`examples/uncertainty-aware/critique-log.md`](examples/uncertainty-aware/critique-log.md)에 기록되어 있습니다.*

## 구조

```
.claude/skills/ml-paper-figure/
├── SKILL.md                    # 트리거 description + 4단계 실행 프로토콜 + 품질 기준
├── references/
│   ├── design-system.md        # 학회별 캔버스 크기, 레이아웃 간격, 저채도 팔레트, 타이포 위계, ML 도형 메타포, 연결선 규칙
│   └── svg-primitives.md       # 복붙용 <defs>(역할별 화살촉, 벡터 배지, 썸네일), 텍스트 정렬·둥근 직각 경로 공식, 사다리꼴/스택/큐보이드
├── scripts/
│   ├── render_svg.py           # 린트 + PNG/PDF 렌더링 + 검수용 debug/preview 이미지 + PDF 검사 (오프라인)
│   └── svg_geom.py             # 좌표 계산기: 연결선 path, 사다리꼴, 스택, 그리드 썸네일, 라벨 중앙 정렬·폭 검사
└── assets/
    ├── primitives-gallery.svg/.png   # 모든 프리미티브의 렌더링 견본
    └── example-figure1.svg/.png      # 린트를 통과한 완성 예시
examples/uncertainty-aware/     # 검증 실행: 입력 → 블루프린트 → 3회 검수 라운드 → 최종 산출물
```

## 설치

이 저장소에서 작업할 때는 프로젝트 스킬(`.claude/skills/`)로 자동 인식됩니다. 다른 프로젝트에서도 쓰려면 사용자 스킬 디렉터리로 복사하세요.

```bash
cp -r .claude/skills/ml-paper-figure ~/.claude/skills/
```

`.agents/skills/` 규약을 쓰는 에이전트라면 같은 폴더를 그 아래로 복사하면 됩니다.

### 요구 사항
- Python 3.8+
- SVG 렌더러 하나(자동 감지): **Playwright + Chromium**(권장: 정확한 기하 린트), `rsvg-convert`, `inkscape`, `cairosvg`, `resvg`(PNG만)
- 선택: poppler-utils(`pdfinfo`, `pdffonts`, `pdfimages`, `pdftoppm`, `pdftocairo`)는 PDF 검사와 Type 3 폰트 윤곽선 변환에 쓰이고, Pillow는 PNG/PDF 비교에 쓰입니다.

```bash
python3 .claude/skills/ml-paper-figure/scripts/render_svg.py --list-backends
```

## 사용

에이전트에게 평소처럼 요청하면 됩니다. 예: *"이 Methods 섹션으로 NeurIPS용 Figure 1 그려줘"*, *"이 PyTorch 모델 구조도를 논문 그림으로"*.
스크립트는 단독으로도 쓸 수 있습니다.

```bash
python3 .claude/skills/ml-paper-figure/scripts/render_svg.py figures/fig1.svg --target neurips            # 검수: png + debug + preview + 린트 보고
```

```bash
python3 .claude/skills/ml-paper-figure/scripts/render_svg.py figures/fig1.svg --target neurips --export   # 최종: 벡터 pdf + 고해상도 png + PDF 검사
```

```bash
python3 .claude/skills/ml-paper-figure/scripts/svg_geom.py elbow 382,140 412,100 --mode hvh --mid 390 --arrow --marker ah-proposed
```

`--target`: `neurips`, `iclr`, `icml`, `icml-col`, `cvpr`, `cvpr-col`, `eccv`, `acl`, `acl-col`, `aaai`, `aaai-col` 또는 `5.5in`, `397pt` 같은 길이.

## 검증 상태

| 항목 | 상태 |
|---|---|
| Chromium(Node Playwright) 렌더링·정확 린트·debug 오버레이·벡터 PDF | 이 환경에서 검증 |
| Chromium 없을 때의 근사 린트(`--no-browser`) | 검증 |
| Type 3 폰트 → 윤곽선 자동 변환(`pdftocairo`) | 검증 (최종 PDF: 폰트 0, 래스터 0, PNG 대비 차이 1.3 %) |
| rsvg-convert / inkscape / cairosvg / resvg 백엔드, Python Playwright 경로 | 코드 경로만 구현, 이 환경에 미설치라 **미검증** |
