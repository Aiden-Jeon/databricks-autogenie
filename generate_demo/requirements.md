# 리테일 분석 Genie Space 요구사항

## 개요

리테일 분석팀이 자연어를 사용하여 매출 성과, 고객 행동, 상품 인사이트를 탐색할 수 있는 Genie Space를 구축합니다. 비즈니스 사용자가 SQL을 작성하지 않고도 질문할 수 있어야 합니다.

## 데이터 소스

모든 테이블은 Unity Catalog의 `main.autogenie_demo`에 있습니다.

---

## 테이블: main.autogenie_demo.customers

**설명:** 세그먼트 및 지역 데이터가 포함된 고객 프로필.

| 컬럼 | 타입 | 설명 |
|--------|------|-------------|
| `customer_id` | BIGINT | 기본 키 |
| `name` | STRING | 고객 성명 |
| `email` | STRING | 고객 이메일 |
| `segment` | STRING | 고객 세그먼트: Premium, Standard, Basic |
| `region` | STRING | 지역: APAC, Americas, EMEA |
| `signup_date` | DATE | 계정 생성일 |
| `lifetime_value` | DOUBLE | 현재까지 총 지출액 (USD) |

---

## 테이블: main.autogenie_demo.products

**설명:** 가격 및 카테고리 정보가 포함된 상품 카탈로그.

| 컬럼 | 타입 | 설명 |
|--------|------|-------------|
| `product_id` | BIGINT | 기본 키 |
| `product_name` | STRING | 상품 표시명 |
| `category` | STRING | 카테고리: Electronics, Clothing, Home, Sports, Beauty |
| `subcategory` | STRING | 카테고리 내 세부 카테고리 |
| `price` | DOUBLE | 단가 (USD) |
| `cost` | DOUBLE | 원가 (USD) |
| `brand` | STRING | 브랜드명 |
| `is_active` | BOOLEAN | 현재 판매 가능 여부 |

---

## 테이블: main.autogenie_demo.orders

**설명:** 상태 추적 및 결제 정보가 포함된 주문 헤더.

| 컬럼 | 타입 | 설명 |
|--------|------|-------------|
| `order_id` | BIGINT | 기본 키 |
| `customer_id` | BIGINT | FK → customers.customer_id |
| `order_date` | DATE | 주문일 |
| `status` | STRING | 주문 상태: completed, shipped, pending, cancelled, returned |
| `total_amount` | DOUBLE | 주문 총액 (USD) |
| `discount_pct` | DOUBLE | 적용된 할인율 (0-100) |
| `payment_method` | STRING | 결제 수단: credit_card, debit_card, paypal, bank_transfer |

---

## 테이블: main.autogenie_demo.order_items

**설명:** 주문과 상품을 연결하는 주문 상세 항목.

| 컬럼 | 타입 | 설명 |
|--------|------|-------------|
| `item_id` | BIGINT | 기본 키 |
| `order_id` | BIGINT | FK → orders.order_id |
| `product_id` | BIGINT | FK → products.product_id |
| `quantity` | INT | 주문 수량 |
| `unit_price` | DOUBLE | 주문 시점 단가 |
| `subtotal` | DOUBLE | quantity * unit_price |

---

## 테이블: main.autogenie_demo.reviews

**설명:** 평점 및 텍스트 피드백이 포함된 상품 리뷰.

| 컬럼 | 타입 | 설명 |
|--------|------|-------------|
| `review_id` | BIGINT | 기본 키 |
| `product_id` | BIGINT | FK → products.product_id |
| `customer_id` | BIGINT | FK → customers.customer_id |
| `rating` | INT | 평점 1-5점 |
| `review_text` | STRING | 리뷰 텍스트 내용 |
| `review_date` | DATE | 리뷰 작성일 |

---

## 조인 관계

- `orders.customer_id` → `customers.customer_id` (각 주문은 하나의 고객에 속함)
- `order_items.order_id` → `orders.order_id` (각 항목은 하나의 주문에 속함)
- `order_items.product_id` → `products.product_id` (각 항목은 하나의 상품을 참조)
- `reviews.product_id` → `products.product_id` (각 리뷰는 하나의 상품에 대한 것)
- `reviews.customer_id` → `customers.customer_id` (각 리뷰는 한 명의 고객이 작성)

---

## 이 Space가 답변할 수 있어야 하는 비즈니스 질문

### 1. 월별 총 매출은 얼마인가?

완료된 주문의 월별 매출을 계산합니다. 매출 = `status = 'completed'`인 `orders.total_amount`. `order_date`의 월별 그룹화.

**샘플 쿼리:**
```sql
SELECT DATE_TRUNC('month', order_date) AS month, SUM(total_amount) AS revenue
FROM main.autogenie_demo.orders
WHERE status = 'completed'
GROUP BY DATE_TRUNC('month', order_date)
ORDER BY month
```

### 2. 총 지출 기준 상위 고객은 누구인가?

완료된 주문의 총 주문 금액 기준으로 고객 순위를 매깁니다. 고객명, 세그먼트, 지역, 총 지출액을 표시합니다.

**샘플 쿼리:**
```sql
SELECT c.name, c.segment, c.region, SUM(o.total_amount) AS total_spend
FROM main.autogenie_demo.customers c
JOIN main.autogenie_demo.orders o ON c.customer_id = o.customer_id
WHERE o.status = 'completed'
GROUP BY c.name, c.segment, c.region
ORDER BY total_spend DESC
LIMIT 10
```

### 3. 판매 수량 기준 베스트셀러 상품은 무엇인가?

모든 완료된 주문에서 총 판매 수량 기준으로 상품 순위를 표시합니다.

**샘플 쿼리:**
```sql
SELECT p.product_name, p.category, SUM(oi.quantity) AS units_sold
FROM main.autogenie_demo.order_items oi
JOIN main.autogenie_demo.products p ON oi.product_id = p.product_id
JOIN main.autogenie_demo.orders o ON oi.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY p.product_name, p.category
ORDER BY units_sold DESC
```

### 4. 상품 카테고리별 매출 내역은 어떻게 되는가?

완료된 주문의 카테고리별 총 매출.

**샘플 쿼리:**
```sql
SELECT p.category, SUM(oi.subtotal) AS category_revenue
FROM main.autogenie_demo.order_items oi
JOIN main.autogenie_demo.products p ON oi.product_id = p.product_id
JOIN main.autogenie_demo.orders o ON oi.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY category_revenue DESC
```

### 5. 카테고리별 평균 상품 평점은 얼마인가?

카테고리별 평균 리뷰 평점과 리뷰 수를 표시합니다.

**샘플 쿼리:**
```sql
SELECT p.category, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(*) AS review_count
FROM main.autogenie_demo.reviews r
JOIN main.autogenie_demo.products p ON r.product_id = p.product_id
GROUP BY p.category
ORDER BY avg_rating DESC
```

### 6. 고객 세그먼트별 매출은 얼마인가?

Premium, Standard, Basic 고객 세그먼트 간 매출을 비교합니다.

**샘플 쿼리:**
```sql
SELECT c.segment, COUNT(DISTINCT o.order_id) AS order_count, SUM(o.total_amount) AS revenue
FROM main.autogenie_demo.customers c
JOIN main.autogenie_demo.orders o ON c.customer_id = o.customer_id
WHERE o.status = 'completed'
GROUP BY c.segment
ORDER BY revenue DESC
```

### 7. 상품별 매출총이익률은 얼마인가?

이익률 계산: 각 상품의 (price - cost) / price, 총 판매 수량과 함께 표시.

**샘플 쿼리:**
```sql
SELECT p.product_name, p.price, p.cost,
       ROUND((p.price - p.cost) / p.price * 100, 1) AS margin_pct,
       SUM(oi.quantity) AS units_sold
FROM main.autogenie_demo.products p
JOIN main.autogenie_demo.order_items oi ON p.product_id = oi.product_id
JOIN main.autogenie_demo.orders o ON oi.order_id = o.order_id
WHERE o.status = 'completed'
GROUP BY p.product_name, p.price, p.cost
ORDER BY margin_pct DESC
```

### 8. 주문 취소 및 반품률은 얼마인가?

전체 주문 대비 취소 또는 반품된 주문의 비율을 표시합니다.

**샘플 쿼리:**
```sql
SELECT status, COUNT(*) AS order_count,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
FROM main.autogenie_demo.orders
GROUP BY status
ORDER BY order_count DESC
```

### 9. 어느 지역이 가장 많은 매출을 올리는가?

고객 지역별(APAC, Americas, EMEA) 매출 분석.

**샘플 쿼리:**
```sql
SELECT c.region, SUM(o.total_amount) AS revenue, COUNT(DISTINCT o.order_id) AS orders
FROM main.autogenie_demo.customers c
JOIN main.autogenie_demo.orders o ON c.customer_id = o.customer_id
WHERE o.status = 'completed'
GROUP BY c.region
ORDER BY revenue DESC
```

### 10. 가장 많이 사용되는 결제 수단은 무엇인가?

완료된 주문의 결제 수단별 주문 수를 집계합니다.

**샘플 쿼리:**
```sql
SELECT payment_method, COUNT(*) AS order_count, SUM(total_amount) AS total_revenue
FROM main.autogenie_demo.orders
WHERE status = 'completed'
GROUP BY payment_method
ORDER BY order_count DESC
```

---

## 추가 지침

- 사용자가 "매출" 또는 "판매"에 대해 질문하면, 완료된 주문(status = 'completed')의 `orders` 테이블에서 `total_amount`를 사용하세요
- 사용자가 "이익" 또는 "마진"을 언급하면, `(price - cost) / price`로 계산하세요
- 기본 기간: 사용자가 특정 기간을 지정하지 않으면 전체 데이터를 표시하세요
- "상위" 또는 "최고" 쿼리는 별도 지정이 없으면 LIMIT 10을 기본으로 사용하세요
- 고객 "가치"는 주문 총액이 아닌 customers 테이블의 `lifetime_value`를 참조합니다
