"""
AutoGenie 데모용 Databricks 워크스페이스에 데모 데이터를 삽입합니다.

현실적인 리테일 분석 데이터셋을 생성합니다:
  - 500명의 고객
  - 100개의 상품
  - 5,000건의 주문
  - 약 12,000건의 주문 상세 항목
  - 3,000건의 리뷰

사용법:
    python generate_demo/insert_data.py --profile <프로필명> --catalog main --schema autogenie_demo
    python generate_demo/insert_data.py --profile <프로필명> --catalog main --schema autogenie_demo --cleanup
"""

import argparse
import subprocess
import json
import sys
import random
from datetime import date, timedelta

# 재현성을 위한 시드 설정
random.seed(42)

# --- 데이터 생성기 ---

FIRST_NAMES_JP = [
    "Yuki", "Hana", "Ren", "Aoi", "Sota", "Mei", "Haruto", "Sakura", "Riku", "Yuna",
    "Kaito", "Hinata", "Takumi", "Mio", "Yuto", "Akari", "Hayato", "Kokona", "Sora", "Riko",
    "Daiki", "Miyu", "Kenta", "Nanami", "Shota", "Rina", "Ryota", "Saki", "Kenji", "Yui",
]
LAST_NAMES_JP = [
    "Tanaka", "Suzuki", "Sato", "Takahashi", "Watanabe", "Yamamoto", "Nakamura", "Kobayashi",
    "Kato", "Yoshida", "Yamada", "Sasaki", "Yamaguchi", "Matsumoto", "Inoue", "Kimura",
    "Shimizu", "Hayashi", "Saito", "Mori", "Ikeda", "Hashimoto", "Abe", "Ishikawa", "Ogawa",
]
FIRST_NAMES_KR = [
    "Minjun", "Soyeon", "Jiho", "Yuna", "Seojin", "Haeun", "Dohyun", "Siwoo", "Jiwoo", "Chaeyoung",
    "Hyunwoo", "Minji", "Jungwoo", "Yerin", "Taehyun", "Somin", "Gunwoo", "Dahyun", "Junseo", "Nayeon",
]
LAST_NAMES_KR = ["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim"]
FIRST_NAMES_EN = [
    "James", "Emma", "Oliver", "Sophia", "Liam", "Isabella", "Noah", "Mia", "Ethan", "Charlotte",
    "Lucas", "Amelia", "Mason", "Harper", "Logan", "Evelyn", "Alexander", "Abigail", "Benjamin", "Emily",
    "Daniel", "Elizabeth", "Henry", "Sofia", "Sebastian", "Avery", "Jack", "Ella", "Owen", "Scarlett",
]
LAST_NAMES_EN = [
    "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Anderson", "Taylor",
    "Thomas", "Moore", "Jackson", "Martin", "White", "Harris", "Thompson", "Clark", "Lewis", "Robinson",
]

SEGMENTS = ["Premium", "Standard", "Basic"]
SEGMENT_WEIGHTS = [0.2, 0.5, 0.3]
REGIONS = ["APAC", "Americas", "EMEA"]
REGION_WEIGHTS = [0.5, 0.3, 0.2]

CATEGORIES = {
    "Electronics": {
        "subcategories": ["Audio", "Computers", "Smart Home", "Wearables", "Cameras", "Accessories"],
        "brands": ["TechBrand", "SoundPro", "DigiMax", "SmartLife", "PixelCore"],
        "price_range": (29.99, 2499.99),
        "margin_range": (0.25, 0.55),
    },
    "Clothing": {
        "subcategories": ["Tops", "Bottoms", "Dresses", "Outerwear", "Activewear", "Formal"],
        "brands": ["StyleCo", "UrbanFit", "ClassicWear", "ModernThread", "EcoFashion"],
        "price_range": (19.99, 399.99),
        "margin_range": (0.50, 0.75),
    },
    "Sports": {
        "subcategories": ["Footwear", "Equipment", "Accessories", "Outdoor", "Fitness"],
        "brands": ["SportMax", "AthleticPro", "TrailMaster", "FitGear", "PeakPerform"],
        "price_range": (14.99, 349.99),
        "margin_range": (0.40, 0.70),
    },
    "Beauty": {
        "subcategories": ["Skincare", "Makeup", "Haircare", "Fragrance", "Tools"],
        "brands": ["NaturGlow", "PureSkin", "GlowLab", "LuxBeauty", "VitaGlow"],
        "price_range": (9.99, 149.99),
        "margin_range": (0.60, 0.85),
    },
    "Home": {
        "subcategories": ["Decor", "Lighting", "Kitchen", "Bedding", "Storage", "Garden"],
        "brands": ["HomeCraft", "CozyLiving", "ModernHome", "GreenSpace", "ArtisanCo"],
        "price_range": (12.99, 299.99),
        "margin_range": (0.45, 0.70),
    },
}

PRODUCT_ADJECTIVES = [
    "Premium", "Ultra", "Pro", "Classic", "Deluxe", "Essential", "Advanced", "Slim",
    "Compact", "Wireless", "Smart", "Eco", "Organic", "Natural", "Luxury", "Lite",
    "Max", "Mini", "Studio", "Elite",
]
PRODUCT_NOUNS = {
    "Audio": ["Headphones", "Earbuds", "Speaker", "Soundbar", "Microphone"],
    "Computers": ["Laptop", "Tablet", "Monitor", "Keyboard", "Mouse"],
    "Smart Home": ["Speaker", "Camera", "Thermostat", "Light Bulb", "Door Lock"],
    "Wearables": ["Fitness Band", "Smartwatch", "Sleep Tracker", "Heart Monitor"],
    "Cameras": ["DSLR Camera", "Action Camera", "Drone", "Instant Camera", "Lens Kit"],
    "Accessories": ["USB Hub", "Charger", "Cable Set", "Phone Case", "Screen Protector"],
    "Tops": ["T-Shirt", "Button Shirt", "Polo", "Blouse", "Sweater", "Hoodie"],
    "Bottoms": ["Jeans", "Chinos", "Shorts", "Skirt", "Leggings"],
    "Dresses": ["Evening Dress", "Casual Dress", "Maxi Dress", "Shirt Dress"],
    "Outerwear": ["Down Jacket", "Blazer", "Raincoat", "Parka", "Trench Coat"],
    "Activewear": ["Running Tights", "Sports Bra", "Tank Top", "Track Jacket"],
    "Formal": ["Suit Jacket", "Dress Pants", "Tie", "Cufflinks Set"],
    "Footwear": ["Running Shoes", "Trail Shoes", "Sneakers", "Hiking Boots", "Sandals"],
    "Equipment": ["Yoga Mat", "Dumbbells", "Resistance Band", "Jump Rope", "Pull-Up Bar"],
    "Outdoor": ["Tent", "Sleeping Bag", "Backpack", "Camping Chair", "Lantern"],
    "Fitness": ["Exercise Bike", "Treadmill Mat", "Foam Roller", "Kettlebell"],
    "Skincare": ["Face Cream", "Serum", "Sunscreen", "Cleanser", "Toner", "Eye Cream"],
    "Makeup": ["Foundation", "Lipstick", "Mascara", "Eye Palette", "Blush"],
    "Haircare": ["Shampoo", "Conditioner", "Hair Oil", "Styling Gel", "Hair Mask"],
    "Fragrance": ["Eau de Parfum", "Body Mist", "Cologne", "Scented Candle"],
    "Tools": ["Hair Dryer", "Straightener", "Brush Set", "Makeup Mirror"],
    "Decor": ["Plant Pot", "Wall Art", "Throw Pillow", "Candle Holder", "Vase"],
    "Lighting": ["Desk Lamp", "Floor Lamp", "Fairy Lights", "Night Light", "Pendant Light"],
    "Kitchen": ["Knife Set", "Cutting Board", "Blender", "Coffee Maker", "Toaster"],
    "Bedding": ["Sheet Set", "Duvet Cover", "Pillow", "Weighted Blanket", "Mattress Pad"],
    "Storage": ["Shelf Unit", "Storage Box", "Drawer Organizer", "Coat Rack"],
    "Garden": ["Planter Box", "Garden Tools Set", "Watering Can", "Bird Feeder"],
}

PAYMENT_METHODS = ["credit_card", "debit_card", "paypal", "bank_transfer"]
PAYMENT_WEIGHTS = [0.45, 0.25, 0.20, 0.10]
ORDER_STATUSES = ["completed", "completed", "completed", "completed", "shipped", "pending", "cancelled", "returned"]

REVIEW_TEMPLATES = {
    5: [
        "정말 마음에 들어요! 올해 최고의 구매입니다.",
        "기대 이상이었습니다. 강력 추천합니다.",
        "완벽한 품질. 망설임 없이 다시 구매할 것입니다.",
        "뛰어난 제품이에요. 별 다섯 개 만점입니다.",
        "가격 대비 놀라운 가치. 매우 만족합니다.",
        "딱 필요했던 것이에요. 완벽하게 작동합니다.",
        "최고급 품질에 배송도 빠릅니다.",
        "가장 좋아하는 구매품이에요. 매일 사용하고 있습니다.",
    ],
    4: [
        "매우 좋은 제품입니다. 약간의 개선 여지가 있어요.",
        "전반적으로 훌륭한 품질. 가격이 약간 비쌉니다.",
        "정말 잘 쓰고 있어요. 포장이 좀 더 나았으면 합니다.",
        "확실한 구매입니다. 기대에 잘 부합합니다.",
        "좋은 제품이에요, 친구들에게 추천하겠습니다.",
        "품질에 만족합니다. 배송이 약간 느렸어요.",
        "디자인과 기능이 좋습니다. 개선의 여지가 있습니다.",
    ],
    3: [
        "괜찮은 제품이에요. 특별하진 않지만 제 역할은 합니다.",
        "가격대에 비해 보통 수준의 품질입니다.",
        "괜찮습니다. 솔직히 좀 더 기대했었어요.",
        "설명대로 작동하지만 좀 저렴한 느낌이 듭니다.",
        "호불호가 갈려요. 어떤 기능은 좋고, 어떤 건 아닙니다.",
        "나쁘진 않지만 이 가격에 다시 사진 않을 것 같아요.",
    ],
    2: [
        "품질이 실망스럽습니다. 더 좋을 줄 알았어요.",
        "가격 대비 가치가 없습니다. 저렴하게 만들어진 느낌이에요.",
        "사용 첫 주에 문제가 생겼습니다.",
        "평균 이하입니다. 추천하지 않겠습니다.",
        "제품이 파손된 상태로 도착했습니다. 고객 서비스도 느렸어요.",
    ],
    1: [
        "품질이 끔찍합니다. 이틀 만에 고장났어요.",
        "완전한 돈 낭비입니다. 매우 실망했습니다.",
        "설명과 전혀 다릅니다.",
        "최악의 구매였습니다. 즉시 반품합니다.",
    ],
}


def generate_customers(n=500):
    """n명의 고객 레코드를 생성합니다."""
    customers = []
    used_emails = set()
    for i in range(1, n + 1):
        region = random.choices(REGIONS, REGION_WEIGHTS)[0]
        segment = random.choices(SEGMENTS, SEGMENT_WEIGHTS)[0]
        if region == "APAC":
            if random.random() < 0.6:
                first = random.choice(FIRST_NAMES_JP)
                last = random.choice(LAST_NAMES_JP)
            else:
                first = random.choice(FIRST_NAMES_KR)
                last = random.choice(LAST_NAMES_KR)
        else:
            first = random.choice(FIRST_NAMES_EN)
            last = random.choice(LAST_NAMES_EN)
        base_email = f"{first.lower()}.{last.lower()}"
        email = f"{base_email}@example.com"
        suffix = 1
        while email in used_emails:
            email = f"{base_email}{suffix}@example.com"
            suffix += 1
        used_emails.add(email)
        signup = date(2022, 1, 1) + timedelta(days=random.randint(0, 900))
        ltv_base = {"Premium": 8000, "Standard": 3000, "Basic": 800}
        ltv = round(random.gauss(ltv_base[segment], ltv_base[segment] * 0.4), 2)
        ltv = max(50, ltv)
        customers.append((i, f"{last} {first}" if region == "APAC" else f"{first} {last}",
                          email, segment, region, str(signup), ltv))
    return customers


def generate_products(n=100):
    """n개의 상품 레코드를 생성합니다."""
    products = []
    used_names = set()
    pid = 101
    for _ in range(n):
        cat = random.choice(list(CATEGORIES.keys()))
        info = CATEGORIES[cat]
        subcat = random.choice(info["subcategories"])
        brand = random.choice(info["brands"])
        nouns = PRODUCT_NOUNS.get(subcat, ["Item"])
        adj = random.choice(PRODUCT_ADJECTIVES)
        noun = random.choice(nouns)
        name = f"{adj} {noun}"
        while name in used_names:
            adj = random.choice(PRODUCT_ADJECTIVES)
            name = f"{adj} {noun}"
        used_names.add(name)
        lo, hi = info["price_range"]
        price = round(random.uniform(lo, hi), 2)
        margin = random.uniform(*info["margin_range"])
        cost = round(price * (1 - margin), 2)
        products.append((pid, name, cat, subcat, price, cost, brand, random.random() > 0.05))
        pid += 1
    return products


def generate_orders(customers, n=5000):
    """18개월에 걸친 n건의 주문을 생성합니다."""
    orders = []
    start = date(2024, 1, 1)
    end = date(2025, 6, 30)
    days_range = (end - start).days
    # Premium 고객은 더 자주 주문합니다
    premium_ids = [c[0] for c in customers if c[3] == "Premium"]
    standard_ids = [c[0] for c in customers if c[3] == "Standard"]
    basic_ids = [c[0] for c in customers if c[3] == "Basic"]
    for oid in range(1001, 1001 + n):
        r = random.random()
        if r < 0.4:
            cid = random.choice(premium_ids)
        elif r < 0.8:
            cid = random.choice(standard_ids)
        else:
            cid = random.choice(basic_ids)
        odate = start + timedelta(days=random.randint(0, days_range))
        status = random.choice(ORDER_STATUSES)
        discount = random.choices([0, 5, 10, 15, 20, 25], [0.50, 0.15, 0.15, 0.10, 0.07, 0.03])[0]
        payment = random.choices(PAYMENT_METHODS, PAYMENT_WEIGHTS)[0]
        # total_amount는 항목에서 계산됨, 현재는 0으로 임시 설정
        orders.append([oid, cid, str(odate), status, 0.0, discount, payment])
    return orders


def generate_order_items(orders, products, avg_items=2.4):
    """주문 상세 항목을 생성합니다."""
    items = []
    item_id = 1
    product_ids = [p[0] for p in products]
    product_prices = {p[0]: p[4] for p in products}
    for order in orders:
        n_items = max(1, int(random.gauss(avg_items, 1.0)))
        n_items = min(n_items, 6)
        chosen = random.sample(product_ids, min(n_items, len(product_ids)))
        order_total = 0.0
        for pid in chosen:
            qty = random.choices([1, 2, 3], [0.70, 0.22, 0.08])[0]
            price = product_prices[pid]
            subtotal = round(qty * price, 2)
            order_total += subtotal
            items.append((item_id, order[0], pid, qty, price, subtotal))
            item_id += 1
        # 주문 총액에 할인 적용
        discount_pct = order[5]
        order[4] = round(order_total * (1 - discount_pct / 100), 2)
    return items


def generate_reviews(customers, products, n=3000):
    """n건의 상품 리뷰를 생성합니다."""
    reviews = []
    customer_ids = [c[0] for c in customers]
    product_ids = [p[0] for p in products]
    start = date(2024, 2, 1)
    end = date(2025, 6, 30)
    days_range = (end - start).days
    for rid in range(1, n + 1):
        pid = random.choice(product_ids)
        cid = random.choice(customer_ids)
        # 평점은 긍정적으로 편향됨 (현실적)
        rating = random.choices([1, 2, 3, 4, 5], [0.03, 0.07, 0.15, 0.35, 0.40])[0]
        text = random.choice(REVIEW_TEMPLATES[rating])
        rdate = start + timedelta(days=random.randint(0, days_range))
        reviews.append((rid, pid, cid, rating, text, str(rdate)))
    return reviews


def escape_sql_str(s):
    """SQL용 작은따옴표를 이스케이프합니다."""
    return str(s).replace("'", "''")


def batch_insert(profile, warehouse_id, table, columns, rows, batch_size=200):
    """VALUES 절을 사용하여 배치 단위로 행을 삽입합니다."""
    total = len(rows)
    for i in range(0, total, batch_size):
        batch = rows[i:i + batch_size]
        values_parts = []
        for row in batch:
            vals = []
            for v in row:
                if v is None:
                    vals.append("NULL")
                elif isinstance(v, bool):
                    vals.append("true" if v else "false")
                elif isinstance(v, (int, float)):
                    vals.append(str(v))
                else:
                    vals.append(f"'{escape_sql_str(v)}'")
            values_parts.append(f"({', '.join(vals)})")
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n" + ",\n".join(values_parts)
        resp = run_sql(profile, warehouse_id, sql)
        state = resp.get("status", {}).get("state", "UNKNOWN")
        if state == "FAILED":
            print(f"  배치 {i // batch_size + 1} 실패", file=sys.stderr)
        pct = min(100, (i + batch_size) * 100 // total)
        print(f"  {table.split('.')[-1]}: {pct}% ({min(i + batch_size, total)}/{total})")


def run_sql(profile: str, warehouse_id: str, sql: str) -> dict:
    """Databricks CLI를 통해 SQL을 실행합니다."""
    result = subprocess.run(
        [
            "databricks", "api", "post",
            "/api/2.0/sql/statements",
            "--profile", profile,
            "--json", json.dumps({
                "warehouse_id": warehouse_id,
                "statement": sql,
                "wait_timeout": "50s",
            }),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  오류: {result.stderr.strip()}", file=sys.stderr)
        return {}
    resp = json.loads(result.stdout)
    status = resp.get("status", {}).get("state", "UNKNOWN")
    if status == "FAILED":
        error = resp.get("status", {}).get("error", {}).get("message", "알 수 없는 오류")
        print(f"  SQL 실패: {error}", file=sys.stderr)
    return resp


def get_warehouse(profile: str) -> str:
    """실행 중인 SQL 웨어하우스를 찾습니다."""
    result = subprocess.run(
        ["databricks", "warehouses", "list", "--profile", profile, "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"웨어하우스 목록 조회 오류: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    warehouses = json.loads(result.stdout)
    if isinstance(warehouses, dict):
        warehouses = warehouses.get("warehouses", [])
    for w in warehouses:
        if w.get("state") == "RUNNING":
            return w["id"]
    if warehouses:
        return warehouses[0]["id"]
    print("SQL 웨어하우스를 찾을 수 없습니다.", file=sys.stderr)
    sys.exit(1)


def create_tables(profile: str, warehouse_id: str, fq: str):
    """모든 테이블을 생성합니다 (DROP + CREATE)."""
    tables = [
        f"""CREATE OR REPLACE TABLE {fq}.customers (
            customer_id BIGINT,
            name STRING,
            email STRING,
            segment STRING COMMENT '고객 세그먼트: Premium, Standard, Basic',
            region STRING COMMENT '지역: APAC, Americas, EMEA',
            signup_date DATE,
            lifetime_value DOUBLE COMMENT '현재까지 총 지출액 (USD)'
        ) COMMENT '세그먼트 및 지역 데이터가 포함된 고객 프로필'""",

        f"""CREATE OR REPLACE TABLE {fq}.products (
            product_id BIGINT,
            product_name STRING,
            category STRING COMMENT '상품 카테고리: Electronics, Clothing, Home, Sports, Beauty',
            subcategory STRING,
            price DOUBLE COMMENT '단가 (USD)',
            cost DOUBLE COMMENT '원가 (USD)',
            brand STRING,
            is_active BOOLEAN
        ) COMMENT '가격 및 카테고리 정보가 포함된 상품 카탈로그'""",

        f"""CREATE OR REPLACE TABLE {fq}.orders (
            order_id BIGINT,
            customer_id BIGINT COMMENT 'FK → customers.customer_id',
            order_date DATE,
            status STRING COMMENT '주문 상태: completed, shipped, pending, cancelled, returned',
            total_amount DOUBLE COMMENT '할인 적용 후 주문 총액 (USD)',
            discount_pct DOUBLE COMMENT '적용된 할인율 (0-100)',
            payment_method STRING COMMENT '결제 수단: credit_card, debit_card, paypal, bank_transfer'
        ) COMMENT '상태 추적 및 결제 정보가 포함된 주문 헤더'""",

        f"""CREATE OR REPLACE TABLE {fq}.order_items (
            item_id BIGINT,
            order_id BIGINT COMMENT 'FK → orders.order_id',
            product_id BIGINT COMMENT 'FK → products.product_id',
            quantity INT,
            unit_price DOUBLE,
            subtotal DOUBLE COMMENT 'quantity * unit_price'
        ) COMMENT '주문과 상품을 연결하는 주문 상세 항목'""",

        f"""CREATE OR REPLACE TABLE {fq}.reviews (
            review_id BIGINT,
            product_id BIGINT COMMENT 'FK → products.product_id',
            customer_id BIGINT COMMENT 'FK → customers.customer_id',
            rating INT COMMENT '평점 1-5점',
            review_text STRING,
            review_date DATE
        ) COMMENT '평점 및 텍스트 피드백이 포함된 상품 리뷰'""",
    ]
    for sql in tables:
        tname = sql.split(f"{fq}.")[1].split(" ")[0].split("\n")[0]
        print(f"  {tname} 생성 중...")
        run_sql(profile, warehouse_id, sql)


def insert_demo_data(profile: str, warehouse_id: str, catalog: str, schema: str):
    """모든 데모 데이터를 생성하고 삽입합니다."""
    fq = f"{catalog}.{schema}"

    print("스키마 생성 중...")
    run_sql(profile, warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {fq}")

    print("테이블 생성 중...")
    create_tables(profile, warehouse_id, fq)

    print("\n데이터 생성 중...")
    customers = generate_customers(500)
    products = generate_products(100)
    orders = generate_orders(customers, 5000)
    order_items = generate_order_items(orders, products)
    reviews = generate_reviews(customers, products, 3000)

    print(f"  생성 완료: 고객 {len(customers)}명, 상품 {len(products)}개, "
          f"주문 {len(orders)}건, 주문 상세 {len(order_items)}건, 리뷰 {len(reviews)}건")

    print("\n데이터 삽입 중...")
    batch_insert(profile, warehouse_id, f"{fq}.customers",
                 ["customer_id", "name", "email", "segment", "region", "signup_date", "lifetime_value"],
                 customers)

    batch_insert(profile, warehouse_id, f"{fq}.products",
                 ["product_id", "product_name", "category", "subcategory", "price", "cost", "brand", "is_active"],
                 products)

    batch_insert(profile, warehouse_id, f"{fq}.orders",
                 ["order_id", "customer_id", "order_date", "status", "total_amount", "discount_pct", "payment_method"],
                 orders)

    batch_insert(profile, warehouse_id, f"{fq}.order_items",
                 ["item_id", "order_id", "product_id", "quantity", "unit_price", "subtotal"],
                 order_items, batch_size=300)

    batch_insert(profile, warehouse_id, f"{fq}.reviews",
                 ["review_id", "product_id", "customer_id", "rating", "review_text", "review_date"],
                 reviews)

    print(f"\n완료! {fq}에 데이터가 삽입되었습니다")
    print(f"  customers:   {len(customers):>6,}")
    print(f"  products:    {len(products):>6,}")
    print(f"  orders:      {len(orders):>6,}")
    print(f"  order_items: {len(order_items):>6,}")
    print(f"  reviews:     {len(reviews):>6,}")
    print(f"  총 행 수:    {sum(len(x) for x in [customers, products, orders, order_items, reviews]):>6,}")


def main():
    parser = argparse.ArgumentParser(description="AutoGenie 데모 데이터를 Databricks에 삽입")
    parser.add_argument("--profile", required=True, help="Databricks CLI 프로필명")
    parser.add_argument("--catalog", default="main", help="대상 카탈로그 (기본값: main)")
    parser.add_argument("--schema", default="autogenie_demo", help="대상 스키마 (기본값: autogenie_demo)")
    parser.add_argument("--warehouse-id", help="SQL 웨어하우스 ID (미지정 시 자동 감지)")
    parser.add_argument("--cleanup", action="store_true", help="데모 스키마 및 모든 테이블 삭제")
    args = parser.parse_args()

    warehouse_id = args.warehouse_id or get_warehouse(args.profile)
    print(f"사용할 웨어하우스: {warehouse_id}")

    if args.cleanup:
        print(f"{args.catalog}.{args.schema} 스키마 삭제 중 (CASCADE)...")
        run_sql(args.profile, warehouse_id, f"DROP SCHEMA IF EXISTS {args.catalog}.{args.schema} CASCADE")
        print("정리 완료.")
    else:
        insert_demo_data(args.profile, warehouse_id, args.catalog, args.schema)


if __name__ == "__main__":
    main()
