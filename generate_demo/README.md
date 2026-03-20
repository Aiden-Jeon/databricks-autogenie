# AutoGenie 데모 생성기

AutoGenie 데모 환경을 완전히 구성하기 위한 스크립트와 에셋입니다.

## 기능

1. **데모 데이터 삽입** - Unity Catalog 테이블에 리테일 분석 데이터셋을 삽입합니다
2. **요구사항 문서 생성** - Lamp 워크플로우용 마크다운 문서
3. **벤치마크 파일 생성** - Lamp 및 Enhancer 워크플로우용 JSON 파일

## 사용법

### 1. 워크스페이스에 데모 데이터 삽입

```bash
# 프로젝트 루트에서 실행
python generate_demo/insert_data.py --profile <프로필명> --catalog main --schema autogenie_demo
```

`main.autogenie_demo`에 5개 테이블이 생성됩니다:
- `customers` - 고객 프로필
- `products` - 상품 카탈로그
- `orders` - 주문 헤더
- `order_items` - 주문 상세 항목
- `reviews` - 상품 리뷰

### 2. 미리 준비된 데모 에셋 사용

데이터 삽입 후, 다음 파일들을 AutoGenie와 함께 사용합니다:

| 파일 | 워크플로우 | 사용 방법 |
|------|----------|------------|
| `requirements.md` | Lamp (업로드 단계) | 요구사항 문서로 업로드 |
| `benchmarks_lamp.json` | Lamp (벤치마크 단계) | 벤치마크 검증용으로 업로드 |
| `benchmarks_enhancer.json` | Enhancer (구성 단계) | 스코어링용으로 업로드 |

### 3. 데모 진행 흐름

**Lamp 워크플로우:**
1. 새로운 Lamp 세션 생성
2. Parse 단계에서 `requirements.md` 업로드
3. 구성 생성 -- AI가 Genie Space 구성을 생성
4. 검증 -- Unity Catalog에 테이블 존재 여부 확인
5. Benchmark 단계에서 `benchmarks_lamp.json` 업로드
6. Genie Space 배포

**Enhancer 워크플로우:**
1. 새로운 Enhancer 세션 생성
2. 배포된 Genie Space와 웨어하우스 선택
3. `benchmarks_enhancer.json` 업로드
4. 스코어링 -- Space에 대해 벤치마크 실행
5. 계획 -- AI가 개선사항 제안
6. 적용 -- Space에 수정사항 적용
7. (선택) 목표 점수까지 자동 반복

## 정리

```bash
python generate_demo/insert_data.py --profile <프로필명> --catalog main --schema autogenie_demo --cleanup
```
