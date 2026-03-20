# Task: Generate SQL Queries for Benchmark Questions

You are an expert SQL analyst. Given a set of tables and benchmark questions, generate accurate SQL queries that answer each question.

## Table Schemas

{table_schemas}

## Join Relationships

{join_specs}

## Benchmark Questions

{benchmark_questions}

## Instructions

For each benchmark question above:
1. Analyze the question and determine which tables/columns are needed
2. Write a SQL query that accurately answers the question
3. Follow SQL best practices:
   - Use proper joins (prefer explicit JOINs over WHERE)
   - Use appropriate aggregations and filters
   - Use explicit table aliases for clarity
   - Add comments for complex logic
4. Ensure SQL is complete and syntactically correct
5. Provide brief reasoning for your query design

## Output Format

Return JSON with this exact structure:
```json
{{
  "benchmark_sqls": [
    {{
      "question": "Original question text (exactly as provided)",
      "sql": "SELECT ... (complete SQL query ending with semicolon)",
      "reasoning": "Brief explanation of query logic"
    }}
  ]
}}
```

**CRITICAL REQUIREMENTS**:
- Every SQL query MUST be complete (no truncation)
- Every SQL query MUST end with a semicolon (;)
- Question text must match exactly
- Include ALL questions from the input
- Generate one SQL query per question
- Do not reuse CTEs or SQL logic across unrelated questions
