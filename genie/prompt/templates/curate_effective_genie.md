# Curate an effective Genie space

The goal of curating a Genie space is to create an environment where business users can pose natural language questions and receive accurate, consistent answers based on their data. Genie spaces use advanced models that generate sophisticated queries and understand general world knowledge.

Most business questions are domain-specific, so a space curator's role is to bridge the gap between that general world knowledge and the specialized language used in a specific domain or by a particular company. Curators use metadata and instructions to help Genie accurately interpret and respond to business users' questions. This article outlines best practices and principles to guide you in developing a successful space.

## Best practices for defining a new space

Keep these guiding principles in mind as you build your Genie space:

* **Provide concise, focused datasets**: Resolve column ambiguities and pre-join or de-normalize tables using views or metric views. Simplified datasets improve Genie's ability to answer data questions accurately.
* **Prioritize SQL expressions and example SQL over text instructions**: Use SQL expressions to define business semantics like metrics and filters. Use example SQL to teach Genie how to handle common ambiguous prompts. Reserve text instructions for general guidance that doesn't fit structured definitions.
* **Write clear, specific text instructions**: Avoid vague instructions. For example, instead of "Ask clarification questions when asked about sales," write "When users ask about sales metrics without specifying product name or sales channel, ask: To proceed with sales analysis, specify your product name and sales channel."
* **Avoid conflicting instructions**: Ensure consistency across all instruction types. For example, if text instructions specify rounding decimals to two digits, then example SQL queries must also round to two digits.

The following sections provide detailed recommendations for building spaces and resolving accuracy challenges.

### Start small

Curating a Genie space is an iterative process. When creating a new space, start as small as possible, with minimal instructions and a limited set of questions to answer. Then, you can add as you iterate based on feedback and monitoring. This approach helps streamline creating and maintaining your space and allows you to curate it effectively in response to real user needs.

Use the following guidelines to help create a small Genie space:

* **Stay focused**: Include only the tables necessary to answer the questions you want the space to handle. Aim for five or fewer tables. The more focused your selection, the better. Keeping your space narrowly focused on a small amount of data is ideal, so limit the number of columns in your included tables.
* **Work within the 25 table limit**: Genie spaces support up to 25 tables or views. If your data topic requires more than 25 tables, prejoin related tables into views or metric views before adding them to your space. Metric views are particularly effective for Genie spaces because they pre-define metrics, dimensions, and aggregations. This approach helps you stay within the limit, simplifies your data model, and can improve Genie's response accuracy.
* **Plan to iterate**: Start with a minimal setup for your space, focusing on essential tables and basic instructions. Add more detailed guidance and examples as you refine the space over time, rather than aiming for perfection initially.
* **Build on well-annotated tables**: Genie uses Unity Catalog column names and descriptions to generate responses. Clear column names and descriptions help produce high-quality responses. Column descriptions should offer precise contextual information. Avoid ambiguous or unnecessary details. Inspect any AI-generated descriptions for accuracy and clarity, and use them only if they align with what you would manually provide.

### Have a domain expert define the space

An effective space creator needs to understand the data and the insights that can be gleaned from it. Data analysts who are proficient in SQL typically have the knowledge and skills to curate the space.

### Define the purpose of your space

Identifying your space's specific audience and purpose helps you decide which data, instructions, and test questions to use. A space should answer questions for a particular topic and audience, not general questions across various domains. You can simplify your datasets by prejoining tables and removing unnecessary columns before adding data to a space. As you add data to your space, keep it tightly focused on the space's defined purpose. Hide any columns that might be confusing or unimportant.

### Add metadata and synonyms

You can add column synonyms and custom descriptions to data in a Genie space. This metadata is scoped to your Genie space and does not overwrite metadata stored in Unity Catalog. Quality column descriptions and synonyms help Genie understand the column better, choose it for relevant questions, and write more accurate SQL.

### Use Genie data sampling

Data sampling improves Genie's accuracy by sampling values from datasets in the space, helping it better match user prompts to the correct columns and values. Genie automatically samples values from tables as you create the space. You can manage which columns have data sampled.

### Provide focused examples and instructions

Genie spaces perform best with a limited, focused set of instructions. Databricks recommends leveraging example SQL queries to provide instructions in your space. Example SQL queries allow Genie to match user prompts to verified SQL queries and learn from examples to answer related questions.

For context that should be applied globally in the Genie space, a small, well-organized set of plain text instructions can also help maintain relevance and improve response quality. Too many instructions can reduce effectiveness, especially in longer conversations, because Genie might struggle to prioritize the most important guidance.

### Choose the right instruction type

Use the following guidelines to decide between SQL expressions and example SQL queries:

* **Use SQL expressions for common business terms**: When defining frequently used metrics, filters, or dimensions that represent standard business concepts, use SQL expressions in the knowledge store. SQL expressions are efficient, reusable definitions that help Genie understand your business logic. Examples include gross margin, recent sales, and conversion rate.
* **Use example SQL queries for complex questions**: When addressing hard-to-interpret, multi-part, or complex questions, provide complete example SQL queries. These examples show Genie how to handle intricate query patterns and multi-step logic. For example, you might create SQL queries for prompts like "breakdown my team's performance" or "For customers who've only joined recently, what products are doing the best?".

### Prompt Genie to ask clarification questions

To prompt Genie to ask clarification questions in certain scenarios, be explicit about when to ask for clarifications and how to follow up. Use clear, specific instructions that define both the triggering conditions and the expected clarification behavior.

For example, add the following type of instruction to your space:

> When users ask about sales performance breakdown but don't include time range, sales channel, or which KPIs in their prompt, you must ask a clarification question first to gather necessary information. For example: "Please specify the time range and sales channel you are looking for."

Structure your clarification instructions with these components:

* **Trigger condition**: Define what topics or scenarios require clarification (for example, "When users ask about X topic...")
* **Missing details**: Specify what information must be present (for example, "...but don't include Y details...")
* **Required action**: State that Genie must ask for clarification (for example, "...you must ask a clarification question first...")
* **Example clarification**: Provide the specific question Genie should ask (for example, "Please specify...")

Add clarification question instructions at the end of your general instructions to help Genie prioritize this behavior when responding to ambiguous questions.

### Test and adjust

You should be your space's first user. After you create a new space, start asking questions. Carefully examine the SQL generated in response to your questions. If Genie misinterprets the data, questions, or business jargon, you can intervene by editing the generated SQL or providing other specific instructions. Keep testing and editing until you're getting reliable responses.

After you've reviewed a question, you can add it as a benchmark question that you can use to test and score your space for overall accuracy systematically. You can use variations and different question phrasings to test Genie's responses.

### Conduct user testing

After verifying response quality through testing, recruit a business user to try the Genie space. Use the following guidelines to provide a smooth user journey and collect feedback for ongoing improvement:

* Set expectations that their job is to help refine the space.
* Ask them to focus their testing on the specific topic and questions the space is designed to answer.
* If they receive an incorrect response, encourage users to add additional instructions and clarifications in the chat to refine the answer. When a correct response is provided, they should upvote the final query to minimize similar errors in future interactions.
* Tell users to upvote or downvote responses using the built-in feedback mechanism.
* Invite users to share additional feedback and unresolved questions directly with the space authors. Authors and editors can use feedback to refine instructions, examples, and trusted assets.

Consider providing training materials or a written document with guidelines for testing the space and providing feedback.

As business users test the space, users with at least CAN MANAGE permissions can see the questions they've asked on the **Monitoring** tab. Continue adding context to help Genie correctly interpret the questions and data to provide accurate answers.

**Note**: Business users must be members of the originating workspace to access your space.

## Metric Views for Pre-Aggregation

Metric views are particularly effective for Genie spaces because they pre-define metrics, dimensions, and aggregations. Consider recommending metric views when:

* Data requires pre-aggregation (daily summaries, running totals)
* Multiple tables need pre-joining
* Complex business logic should be encapsulated
* The space would otherwise exceed 25 tables

This approach helps you stay within the limit, simplifies your data model, and can improve Genie's response accuracy.

## Knowledge Store Configuration

### Entity Matching (for categorical columns)

Enable entity matching for columns with discrete values to significantly improve reliability:
* State/country codes
* Product categories
* Status codes
* Department names

**Limitation**: Cannot be enabled on tables with row filters or column masks.

### Column Visibility Strategy

* **Hide** unnecessary columns that might confuse Genie
* Keep only columns essential for the defined purpose
* Use descriptions and synonyms to clarify remaining columns

### Metadata Customization

* Add space-scoped synonyms (doesn't affect Unity Catalog)
* Provide custom descriptions for columns
* Map business terminology to technical column names

## Throughput and Capacity Limits

Be aware of these limits when planning your Genie space:

* **Table limit**: Maximum 25 tables or views per space
* **API throughput**: 5 queries per minute per workspace (Public Preview)
* **UI throughput**: Up to 20 questions per minute
* **Conversation limit**: 10,000 conversations maximum per space
* **Query result limit**: Maximum 5,000 rows returned per query

## Common Issues and Preventive Guidance

### Filtering Errors
* Enable entity matching for categorical columns
* Document expected value formats in instructions
* Example: "Filter by `status` column. Values use uppercase: 'ACTIVE', 'INACTIVE'"

### Join Errors
* Define ALL join relationships explicitly
* Provide clear guidance for when to use each join
* Consider pre-joining tables into views for complex relationships

### Ignored Instructions
When Genie ignores text instructions:
1. Provide example SQL queries (most effective teaching method)
2. Hide irrelevant columns to reduce confusion
3. Simplify data model with views
4. Review instruction count - too many can reduce effectiveness

### Misunderstood Jargon
* Map business terminology explicitly in instructions
* Add synonyms for commonly used terms
* Provide example SQL that demonstrates correct column/table usage
