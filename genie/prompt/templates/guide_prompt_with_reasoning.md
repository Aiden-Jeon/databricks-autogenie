# Instruction

You are an expert in creating Databricks Genie spaces. Your task is to analyze the provided requirements document and generate a comprehensive Genie space configuration that follows best practices.

## Genie Space Best Practices - Do's and Don'ts

### Do's ✅

**✅ Teach Genie when to ask clarifications**
- Help Genie understand when user prompts are missing necessary context
- Example: "When users ask about revenue without specifying time period, ask: 'Which time period would you like to analyze? (e.g., last 7 days, last month, Q1 2024)'"

**✅ Add formatting instructions**
- Teach Genie how to format numeric results, which language to respond in, or how many rows to include
- Example: "Round all monetary values to 2 decimal places", "Default to top 10 results unless specified"

**✅ Concise and direct**
- Text should be phrased as explicit directions: "When the user… make sure to…", "Always include…"
- Avoid vague or ambiguous language

**✅ Organize as a list**
- Use dashes/asterisks to make instructions easier for collaboration and for Genie to understand
- Use markdown headers (##) to group related instructions

**✅ Prioritize SQL expressions and example SQL**
- Use SQL expressions to define business semantics like metrics and filters
- Use example SQL to teach Genie how to handle common ambiguous prompts
- Reserve text instructions for general guidance that doesn't fit structured definitions

### Don'ts ❌

**❌ Don't overload text**
- Text isn't filtered by prompt; this uses context space and makes conflicting context more likely
- Keep instructions focused and essential only
- Start with 5-15 instruction items. Up to 100 total allowed, but more instructions can reduce effectiveness
- If instructions exceed 15 items, verify each one is truly necessary and not duplicating SQL expressions

**❌ Avoid conflicting instructions**
- Like telling a new data analyst two ways to answer the same question—it'll confuse the LLM
- Ensure consistency across all instruction types (text, SQL expressions, example SQL)
- Example: If text says "round to 2 decimals", all SQL must also round to 2 decimals

**❌ Don't enumerate column values**
- This wastes context space and becomes outdated quickly
- Instead: Let Genie use value dictionaries and data sampling
- Example: DON'T write "status can be: 'active', 'inactive', 'pending', 'cancelled', 'completed'..."
- Instead: Write "Filter by status column for order lifecycle tracking"

**❌ Don't add SQL logic as text**
- Prioritize Example SQL and SQL Primitives (expressions, measures, filters) to teach Genie SQL logic
- Example: DON'T write "To calculate revenue, sum the amount column and multiply by quantity"
- Instead: Create a SQL expression: `SUM(amount * quantity) as total_revenue`

---

## Query Parameters for Trusted Responses

When creating parameterized SQL queries, use named parameter markers with colon prefix. Parameterized queries enable the "Trusted" response label, signaling verified SQL to users.

**Syntax**: `:parameter_name`

**Example**:
```sql
SELECT * FROM orders
WHERE region = :region_code
  AND order_date BETWEEN :start_date AND :end_date
```

**Parameter Types**:
- **String** (default): Text values
- **Date**: Date values (format: yyyy-MM-dd)
- **Numeric**: Decimal or Integer values

**Best Practice**: Use parameterized queries for frequently asked questions with variable inputs. Include type specifications and clear parameter names that match business terminology.

---

## Knowledge Store Configuration

### Entity Matching (for Categorical Columns)

Enable entity matching for columns with discrete values to significantly improve Genie's reliability:
- State/country codes
- Product categories
- Status codes (e.g., 'ACTIVE', 'INACTIVE', 'PENDING')
- Department names

**Limitation**: Entity matching cannot be enabled on tables with row filters or column masks.

### Column Visibility Strategy

- **Hide** unnecessary columns that might confuse Genie
- Keep only columns essential for the defined purpose
- Use descriptions and synonyms to clarify remaining columns
- Reducing column count improves response accuracy

### Metadata Customization

- Add space-scoped synonyms (doesn't affect Unity Catalog)
- Provide custom descriptions for columns
- Map business terminology to technical column names
- Example: Add synonym "revenue" for column "total_amount"

---

## When to Recommend Metric Views

Consider recommending metric views when the requirements indicate:
- Data requires pre-aggregation (daily summaries, running totals)
- Multiple tables need pre-joining for common query patterns
- Complex business logic should be encapsulated
- The space would otherwise exceed 25 tables

Metric views pre-define:
- **Metrics** (measures): Pre-calculated aggregations
- **Dimensions** (grouping attributes): Standard grouping columns
- **Aggregations** (pre-computed summaries): Common rollups

This improves Genie's response accuracy for complex analytical questions by simplifying the data model.

---

## Common Issues and Preventive Instructions

Generate instructions that preemptively address these common Genie failures:

### Filtering Errors
- Enable entity matching for categorical columns
- Document expected value formats in instructions
- Example instruction: "Filter by `status` column. Values use uppercase: 'ACTIVE', 'INACTIVE', 'PENDING'"

### Join Errors
- Define ALL join relationships in `join_specifications`
- Provide clear `instruction` field for when to use each join
- Consider pre-joining tables into views for complex relationships
- Example: "When analyzing customer orders, ALWAYS join customers to orders using customer_id"

### Timezone Handling
- Always specify timezone conversion in instructions when relevant
- Example: "Convert timestamps using `convert_timezone('UTC', 'America/Los_Angeles', timestamp_col)`"
- Document the expected timezone for date filters

### Ignored Instructions
When Genie ignores text instructions, the solution hierarchy is:
1. **Provide example SQL queries** (most effective teaching method)
2. **Hide irrelevant columns** to reduce confusion
3. **Simplify data model with views**
4. **Review instruction count** - too many can reduce effectiveness

### Value Format Mismatches
- Document exact formats for common filters
- Example: "Date format is 'YYYY-MM-DD'. For 'last month', use DATE_SUB(CURRENT_DATE(), 30)"
- Include case sensitivity notes: "Product codes are uppercase (e.g., 'SKU-001')"

---

## Benchmark Questions (Handled Separately)

**Note**: Benchmarks are loaded from external JSON files (`benchmarks/benchmarks.json`), not generated in this configuration.

When creating benchmarks separately, follow these guidelines:
- Include **2-4 phrasings** of the same question to test robustness
- Use the same expected SQL across related phrasings
- Cover frequently asked user questions
- Test edge cases (empty results, NULL handling, boundary dates)

Example benchmark structure:
```json
{{
  "question": "What were our top 10 customers by revenue last month?",
  "expected_sql": "SELECT customer_name, SUM(amount) as total FROM orders WHERE date >= DATE_SUB(CURRENT_DATE(), 30) GROUP BY customer_name ORDER BY total DESC LIMIT 10"
}}
```

---

## Your Task

Based on the input requirements, you should:

1. Identify the key tables needed for the Genie space
2. Define SQL snippets for reusable components:
   - **Filters**: WHERE conditions (e.g., "table.price > 100", "status = 'active'")
   - **Expressions**: Dimensions/calculated fields (e.g., "YEAR(order_date)", "CONCAT(first_name, ' ', last_name)")
   - **Measures**: Aggregations (e.g., "SUM(revenue)", "COUNT(DISTINCT customer_id)", "AVG(price)")
   - Create 5-15 snippets total, focusing on commonly used business terms and calculations
   - Quality and relevance over quantity
   - **Add optional instructions**: For complex or ambiguous metrics, provide a brief instruction (1-3 sentences) that explains:
     - **What should this measure/expression do?** (its purpose, e.g., "Calculates total revenue across all completed orders")
     - **How should it behave?** (usage guidance, e.g., "Use for monthly revenue tracking. Groups by transaction date.")
     - **What should it avoid?** (caveats/exclusions, e.g., "Excludes refunded orders and test transactions. Do not use for forecasting.")
3. Write clear, specific instructions to guide Genie's behavior
   - Focus on WHEN to use certain columns or patterns, not enumerating all possible values
   - Example: "Use `status` column to filter order lifecycle" instead of listing all status values
   - Genie uses data sampling to understand column values automatically
   - Reserve instructions for behavior guidance, not data dictionaries

**IMPORTANT NOTES**:
- **Do NOT generate example_sql_queries** - These are extracted separately from requirements documents
- **Do NOT generate benchmark_questions** - These are also extracted and processed separately by the system
- Leave both `example_sql_queries` and `benchmark_questions` as empty arrays

Follow these principles:
- Keep the space focused but comprehensive (aim for 5-15 tables depending on requirements scope - include all tables needed to answer the key questions in the FAQ)
- Prioritize SQL expressions and example SQL over text instructions
- Write clear, specific instructions (avoid vague guidance)
- **Keep instructions concise** - Aim for 5-15 instruction items total; more than that indicates overload
- Ensure consistency across all instruction types (if one place says "round to 2 decimals", ALL SQL must do the same)
- Define the purpose and target audience clearly
- **Document all join relationships explicitly** - Never rely on implicit join knowledge
- **Validate SQL correctness** - All SQL must reference existing columns with correct syntax
- **Use markdown formatting in instructions**: Structure your instruction content using markdown for clarity:
  - Use `##` for section headings to organize related instructions
  - Use bullet lists (`-`) for multiple related points
  - Use **bold** for emphasis on critical terms or actions
  - Use `code blocks` or inline `code` for column names, table names, or SQL keywords
  - Use numbered lists for sequential steps or priorities

Your output MUST be a valid JSON object matching the GenieSpaceConfig schema.

## Critical Requirements for SQL Quality

When generating SQL expressions and example queries, you MUST follow these SQL quality standards:

### 1. Use Correct Column References
- **ONLY reference columns that exist** in the specified tables from the requirements
- Use **fully qualified names**: `catalog.schema.table.column`
- Verify column names match the requirements document **exactly**
- Never assume column names - use the exact names provided

### 2. Explicit Join Conditions (CRITICAL)
- For **every multi-table query**, specify JOIN conditions explicitly
- Use the join relationships documented in the requirements
- Prefer **INNER JOIN** for required relationships, **LEFT JOIN** for optional
- **Always specify ON clauses** with exact foreign key relationships
- Example: `INNER JOIN catalog.schema.customers c ON t.customer_id = c.customer_id`

### 3. Aggregation Correctness
- Use appropriate **GROUP BY** for all non-aggregated columns in SELECT
- Include proper NULL handling: `COALESCE()`, `NULLIF()` for divisions
- Use correct aggregate functions:
  - `SUM()` for totals
  - `COUNT(DISTINCT column)` for uniqueness counts
  - `AVG()` for averages

### 4. Filter Precision
- Use correct **date functions**: `CURRENT_DATE()`, `DATE_SUB()`, `DATE_TRUNC()`
- Apply filters on the right columns (e.g., `event_date` vs `timestamp` fields)
- Include necessary WHERE clauses for data quality (e.g., `status != 'cancelled'`)
- Example: `WHERE event_date >= DATE_SUB(CURRENT_DATE(), 30)`

### 5. Output Formatting
- Cast decimals explicitly: `CAST(... AS DECIMAL(38,2))`
- Use `try_divide()` for safe division operations to handle nulls
- Include appropriate **LIMIT clauses** for top-N queries
- Order results meaningfully with **ORDER BY**

### 6. Query Structure Best Practices
- Use meaningful table aliases (e.g., `t` for transactions, `c` for customers)
- Format SQL for readability (proper indentation, line breaks)
- Include comments for complex logic
- Test patterns: Ensure queries are runnable and return expected results

## Examples: High-Quality vs Low-Quality Configurations

### ❌ LOW QUALITY - Avoid This

**Vague Instruction:**
```
Use appropriate tables for queries and handle dates correctly.
```

**Poor SQL Example (implicit join, missing conditions):**
```sql
SELECT *
FROM transactions t, customers c
WHERE t.date > '2024-01-01'
```
**Problems:**
- Missing JOIN condition (Cartesian product)
- SELECT * (unclear what columns are needed)
- Implicit comma join instead of explicit JOIN syntax
- Hard-coded date instead of dynamic date function
- No table qualification

### ✅ HIGH QUALITY - Generate This

**Specific, Structured Instruction:**
```markdown
## Transaction Analysis Rules

### Required Joins
- Always join `transactions` to `customers` using `customer_id`
- Join `transactions` to `products` using `product_id` when analyzing product details

### Date Handling
- Default to **last 30 days** when time range not specified
- Use: `WHERE event_date >= DATE_SUB(CURRENT_DATE(), 30)`
- For "today": use `CURRENT_DATE()`
- For "this month": use `DATE_TRUNC('month', CURRENT_DATE())`

### Data Filtering
- **Always filter out cancelled orders**: `status != 'cancelled'`
- For active customers only: `customer_status = 'active'`
- Exclude test transactions: `is_test = false`

### Aggregation Standards
- Round monetary values to 2 decimals: `CAST(amount AS DECIMAL(38,2))`
- Use safe division: `try_divide(revenue, customer_count)`
- Count unique entities with: `COUNT(DISTINCT customer_id)`

## Clarification Questions
When users ask about "performance" without specifying metrics or time period, ask:
> "To analyze performance, please specify: (1) which metrics (revenue, orders, customers), and (2) time period (e.g., last month, Q1 2024)."
```

**Excellent SQL Example (explicit joins, correct aggregation, proper formatting):**
```sql
-- Top 10 customers by revenue in last 30 days
SELECT
  c.customer_id,
  c.customer_name,
  COUNT(DISTINCT t.transaction_id) as transaction_count,
  CAST(SUM(t.amount) AS DECIMAL(38,2)) as total_revenue,
  CAST(try_divide(SUM(t.amount), COUNT(DISTINCT t.transaction_id)) AS DECIMAL(38,2)) as avg_order_value
FROM main.retail.transactions t
INNER JOIN main.retail.customers c
  ON t.customer_id = c.customer_id
WHERE t.event_date >= DATE_SUB(CURRENT_DATE(), 30)
  AND t.status != 'cancelled'
  AND t.is_test = false
GROUP BY c.customer_id, c.customer_name
HAVING total_revenue > 0
ORDER BY total_revenue DESC
LIMIT 10;
```

**Why this is high quality:**
- ✅ Explicit INNER JOIN with ON clause
- ✅ Fully qualified table names (catalog.schema.table)
- ✅ Meaningful column selection (not SELECT *)
- ✅ Correct GROUP BY (includes all non-aggregated columns)
- ✅ Safe aggregation with CAST for decimals and try_divide
- ✅ Dynamic date filtering (not hard-coded)
- ✅ Multiple business rule filters (status, is_test)
- ✅ HAVING clause for post-aggregation filtering
- ✅ Meaningful ORDER BY and LIMIT
- ✅ SQL comment explaining the query purpose

### Example of Well-Formatted Instruction Content

Good markdown formatting example:
```
## Date and Time Handling
- Always use `event_date` column for date-based queries
- Default to **last 30 days** when no time period is specified
- Use `CURRENT_DATE()` for "today" and `DATE_SUB(CURRENT_DATE(), 30)` for "last 30 days"

## Metric Calculations
When calculating **revenue metrics**:
1. Use `total_revenue` column (already includes tax)
2. Round all monetary values to 2 decimal places
3. Filter out cancelled orders using `status != 'cancelled'`

## Clarification Questions
When users ask about performance but don't specify time range or product category, ask:
> "To analyze performance, please specify: (1) time period (e.g., last month, Q1 2024), and (2) product category you want to analyze."
```

## Instruction Quality Guidelines

Generate instructions that are **specific, actionable, and well-structured**:

### 1. Be Specific and Concrete (NOT Vague)
❌ **Avoid:** "Handle dates appropriately" or "Use relevant tables"
✅ **Use:** "Use `event_date` column for all date filters. Default to last 30 days: `WHERE event_date >= DATE_SUB(CURRENT_DATE(), 30)`"

❌ **Avoid:** "Ask clarification questions when needed"
✅ **Use:** "When users ask about 'sales' without specifying product category or time range, ask: 'Which product category and time period would you like to analyze?'"

### 2. Structure with Markdown (Already Required)
- Use `##` headers to group related instructions
- Use bullet lists for multiple rules
- Use **bold** for critical terms
- Use `code formatting` for column/table names and SQL keywords

### 3. Prioritize Instructions Correctly
Assign priority values based on impact:
- **Priority 1 (Critical):** Data correctness rules - joins, required filters, date handling
  - Example: "Always filter out `status = 'cancelled'` from transactions"
- **Priority 2 (Important):** Default behaviors, clarification triggers, metric definitions
  - Example: "Default to last 30 days when time range not specified"
- **Priority 3+ (Optional):** Formatting preferences, nice-to-have guidance
  - Example: "Format monetary values with 2 decimal places for presentation"

### 4. Include Explicit Clarification Triggers
When questions could be ambiguous, tell Genie **exactly what to ask**:

**Structure:**
```markdown
When users ask about [TOPIC] without specifying [MISSING_INFO], ask:
> "[EXACT CLARIFICATION QUESTION]"
```

**Example:**
```markdown
When users ask about "customer performance" without specifying time period or metric, ask:
> "To analyze customer performance, please specify: (1) time period (e.g., last quarter, YTD), and (2) which metrics to analyze (revenue, order count, retention rate)."
```

### 5. Avoid Unnecessary Instructions
- Don't state obvious SQL syntax rules
- Don't repeat what's in table/column descriptions
- Don't add instructions that conflict with SQL expressions or examples
- Focus on **domain-specific** and **business-specific** rules only

## Join Specification Requirements (CRITICAL)

For **every pair of tables** that need to be joined together, you MUST document the join relationship in `join_specifications`:

```json
{{
  "join_specifications": [
    {{
      "left_table": "catalog.schema.table1",
      "right_table": "catalog.schema.table2",
      "join_type": "INNER",
      "join_condition": "table1.foreign_key_column = table2.primary_key_column",
      "description": "Explanation of the relationship (e.g., 'Each transaction belongs to one customer')",
      "instruction": "When to use this join (e.g., 'Use this join when analyzing transaction data with customer context')"
    }}
  ]
}}
```

### Join Type Selection:
- **INNER JOIN**: Use when both tables must have matching records (e.g., transactions must have a valid customer)
- **LEFT JOIN**: Use when the right table is optional (e.g., customers may not have transactions)
- **RIGHT JOIN**: Rarely used, prefer LEFT JOIN with swapped tables
- **FULL OUTER JOIN**: Only for specific merge scenarios

### Join Instruction Field (REQUIRED):
The `instruction` field provides guidance on **when and how to use this join**. This helps Genie decide which joins to apply for different types of questions.

**Good instruction examples:**
- ✅ "Use this join when users ask about message engagement or reactions"
- ✅ "Use this join when analyzing customer purchase history or transaction details"
- ✅ "Use this join to enrich products with category information for product analysis questions"
- ✅ "Use LEFT JOIN to keep all messages, even those without reactions"

**Bad instruction examples (too vague):**
- ❌ "how should join this?"
- ❌ "join when needed"
- ❌ "use this join"

### Why Join Specifications Are Critical:
- Genie uses these to understand table relationships
- Prevents Cartesian products and incorrect joins
- Documents the data model explicitly
- Improves SQL generation accuracy significantly
- **Instructions guide Genie on when to apply specific joins based on the user's question**

### Example Join Specifications:
```json
{{
  "join_specifications": [
    {{
      "left_table": "main.retail.transactions",
      "right_table": "main.retail.customers",
      "join_type": "INNER",
      "join_condition": "transactions.customer_id = customers.customer_id",
      "description": "Each transaction is associated with exactly one customer. Use INNER JOIN because all transactions must have a valid customer.",
      "instruction": "Use this join when analyzing customer behavior, customer demographics, or any customer-related transaction analysis"
    }},
    {{
      "left_table": "main.retail.transactions",
      "right_table": "main.retail.products",
      "join_type": "INNER",
      "join_condition": "transactions.product_id = products.product_id",
      "description": "Each transaction references one product. Use INNER JOIN to ensure product details are available.",
      "instruction": "Use this join when users ask about product performance, product categories, or need product details in transaction analysis"
    }},
    {{
      "left_table": "main.retail.customers",
      "right_table": "main.retail.transactions",
      "join_type": "LEFT",
      "join_condition": "customers.customer_id = transactions.customer_id",
      "description": "When analyzing all customers (including those without purchases), use LEFT JOIN to include customers with no transactions.",
      "instruction": "Use this join when analyzing all customers including those who haven't made purchases yet. Use LEFT JOIN to preserve all customer records"
    }}
  ]
}}
```

## Context: Best Practices for Curating a Genie Space

{context_content}

## Output Format: Genie API Documentation

{output_content}

## Input: Requirements Document

{input_content}

# Output

Please generate a complete GenieSpaceConfig JSON object based on the requirements. The JSON should be valid and follow this schema:

```json
{{
  "space_name": "string",
  "description": "string",
  "purpose": "string",
  "tables": [
    {{
      "catalog_name": "string",
      "schema_name": "string",
      "table_name": "string",
      "description": "string (optional)"
    }}
  ],
  "join_specifications": [
    {{
      "left_table": "catalog.schema.table1",
      "right_table": "catalog.schema.table2",
      "join_type": "INNER|LEFT|RIGHT|FULL",
      "join_condition": "table1.column = table2.column",
      "description": "string (explanation of the relationship)",
      "instruction": "string (when to use this join - e.g., 'Use this join when analyzing X with Y context')"
    }}
    // CRITICAL: Include join specs for EVERY pair of related tables
    // This is essential for SQL correctness
    // REQUIRED: Add instruction field to guide when to use each join
  ],
  "instructions": [
    {{{{
      "content": "string (use markdown formatting for better structure - headings, lists, bold, code, etc.)",
      "priority": "integer (1=critical data correctness, 2=important business rules, 3+=optional guidance)"
    }}}}
  ],
  "example_sql_queries": [],
  // DO NOT GENERATE example_sql_queries - they are extracted separately from requirements
  // Leave this as an empty array
  
  "benchmark_questions": [],
  // DO NOT GENERATE benchmark_questions - they are handled separately
  // Leave this as an empty array
  "sql_snippets": {{{{
    "filters": [
      {{{{
        "sql": "string (WHERE condition, e.g., 'table.price > 100')",
        "display_name": "string (user-friendly name)",
        "synonyms": ["string"] (optional, alternative names)
      }}}}
    ],
    "expressions": [
      {{{{
        "alias": "string (internal alias, e.g., 'order_year')",
        "sql": "string (dimension/calculated field, e.g., 'YEAR(orders.order_date)')",
        "display_name": "string (user-friendly name, e.g., 'Order Year')",
        "synonyms": ["string"] (optional, alternative names),
        "instruction": "string (optional - explain what it does, how to use it, and what to avoid. e.g., 'Extracts the calendar year from order date for trend analysis. Use when grouping by year. Do not use for fiscal year calculations.')"
      }}}}
    ],
    "measures": [
      {{{{
        "alias": "string (internal alias, e.g., 'total_revenue')",
        "sql": "string (aggregation, e.g., 'SUM(orders.order_amount)')",
        "display_name": "string (user-friendly name, e.g., 'Total Revenue')",
        "synonyms": ["string"] (optional, alternative names like 'revenue', 'total sales'),
        "instruction": "string (optional - explain what it does, how to use it, and what to avoid. e.g., 'Calculates total revenue from completed orders. Use for revenue reporting and trend analysis. Excludes refunds, cancelled orders, and test transactions. Do not use for cash flow analysis.')"
      }}}}
    ]
  }}}},
  
  // Example SQL snippets with instructions:
  // "expressions": [
  //   {{{{
  //     "alias": "customer_cohort_month",
  //     "sql": "DATE_TRUNC('month', customers.first_purchase_date)",
  //     "display_name": "Customer Cohort Month",
  //     "synonyms": ["cohort", "signup month"],
  //     "instruction": "Extracts the month of customer's first purchase for cohort grouping. Use when analyzing customer cohorts by signup/acquisition period. Do not use for monthly revenue attribution."
  //   }}}}
  // ],
  // "measures": [
  //   {{{{
  //     "alias": "active_user_count",
  //     "sql": "COUNT(DISTINCT CASE WHEN users.last_activity_date >= DATE_SUB(CURRENT_DATE(), 30) THEN users.user_id END)",
  //     "display_name": "Active Users (30d)",
  //     "synonyms": ["MAU", "active customers"],
  //     "instruction": "Counts distinct users with any activity in the last 30 days. Use for monthly active user (MAU) reporting and engagement metrics. Excludes deleted accounts and system users. Do not use for daily active user (DAU) calculations."
  //   }}}}
  // ]
  
  "warehouse_id": "string (optional)",
  "enable_data_sampling": true
}}}}
```

Respond with a JSON object that includes:
1. `genie_space_config`: The complete GenieSpaceConfig object
2. `reasoning`: Your explanation for the configuration choices (string)
3. `confidence_score`: Your confidence in this configuration (float between 0 and 1)

The JSON structure should be:
```json
{{
  "genie_space_config": {{ /* GenieSpaceConfig object */ }},
  "reasoning": "string explaining your choices",
  "confidence_score": 0.95
}}
```

Respond with ONLY the JSON object.
