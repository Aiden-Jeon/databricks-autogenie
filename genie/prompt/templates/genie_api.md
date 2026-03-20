# Use the Genie API to integrate Genie into your applications

**Status**: Public Preview

This page explains how to use the Genie API to enable Genie capabilities in your own chatbot, agent, or application.

## Overview

The Genie API enables developers to integrate natural language data querying into applications, chatbots, and AI agent frameworks. It supports stateful conversations, allowing users to ask follow-up questions and explore data more naturally over time. Using the Genie API, you can integrate natural language querying into your tools and workflows, making data more accessible across the organization.

Before using the API, you must prepare a well-curated Genie space. The space defines the context that Genie uses to interpret questions and return results. If the space is incomplete or untested, users may receive a high rate of incorrect answers, even if the API integration itself is successful. This guide outlines the minimum setup required to create a space that works effectively with the Genie API.

## Prerequisites

To use the Genie conversation API, you must have:

* Access to a Databricks workspace with the Databricks SQL entitlement.
* At least CAN USE privileges on a SQL pro or serverless SQL warehouse.
* Familiarity with the Databricks REST API reference.

## Step 1: Create and test a Genie space

Prepare a Genie space that reliably answers user questions with a high degree of accuracy.

**Note**: Even if you plan to query the Genie space using the API, you must set up and refine the space using the Databricks UI.

Use the following resources to help you configure and curate your Genie space:

1. **Set up a Genie space:** Learn how to create a Genie space using the Databricks UI. This article includes step-by-step guidance for using UI tools to create a working Genie space.
2. **Review best practices:** Learn best practices for curating a new Genie space. This article offers recommendations for how to approach new Genie space creation and how to refine and iterate on a space through testing and feedback.
3. **Set benchmarks:** Prepare benchmark test questions that you can run to measure Genie's response accuracy.

A well-structured Genie space has the following characteristics:

* **Uses well-annotated data:** Genie relies on table metadata and column comments to generate responses. The Unity Catalog data sources for your Genie space should include clear and descriptive comments.
* **Is user tested:** You should be your space's first user. Test your space by asking questions you expect from end users. Use your testing to create and refine example SQL queries.
* **Includes company-specific context:** You need to include context to teach Genie about your company's data and jargon. Aim to include at least 5 example SQL queries that have undergone testing and refinement.
* **Uses benchmarks to test accuracy:** Add at least 5 benchmark questions based on questions you anticipate from end users. Run benchmark tests to verify that Genie is answering those questions accurately.

When you are satisfied with the responses in your Genie space and have tested it with representative questions, you can begin integrating it with your application.

## Step 2: Configure Databricks authentication

For production use cases where a user with access to a browser is present, use OAuth for users (OAuth U2M). In situations where browser-based authentication is not possible, you can use a service principal to authenticate with the API. Service principals must have permissions to access the required data and SQL warehouses.

## Step 3: Gather details

Use the Genie space URL to find your workspace instance name and the Genie space ID. The following example demonstrates how to locate these components in the URL:

```
https://<databricks-instance>/genie/rooms/<space-id>
```

Copy the `<databricks-instance>` and the `<space-id>` for your Genie space. You can also find and copy the space ID from the Genie space **Settings** tab.

### List Genie spaces

Instead of finding the `space-id` in the URL, you can use the List Genie spaces endpoint `GET /api/2.0/genie/spaces` to programatically retrieve a list of all Genie spaces in a workspace that the user has access to. The returned `spaces` array lists each Genie space's description, space ID, and title.

## Step 4: Start a conversation

The Start conversation endpoint `POST /api/2.0/genie/spaces/{space_id}/conversations` starts a new conversation in your Genie space.

Replace the placeholders with your Databricks instance, Genie space ID, and authentication token. An example of a successful response follows the request. It includes details that you can use to access this conversation again for follow-up questions.

```
POST /api/2.0/genie/spaces/{space_id}/conversations  
  
HOST= <DATABRICKS_INSTANCE>  
Authorization: <your_authentication_token>  
{  
    "content": "<your question>",  
}  
  
  
Response:  
  
{  
  "conversation": {  
    "created_timestamp": 1719769718,  
    "id": "6a64adad2e664ee58de08488f986af3e",  
    "last_updated_timestamp": 1719769718,  
    "space_id": "3c409c00b54a44c79f79da06b82460e2",  
    "title": "Give me top sales for last month",  
    "user_id": 12345  
  },  
  "message": {  
    "attachments": null,  
    "content": "Give me top sales for last month",  
    "conversation_id": "6a64adad2e664ee58de08488f986af3e",  
    "created_timestamp": 1719769718,  
    "error": null,  
    "id": "e1ef34712a29169db030324fd0e1df5f",  
    "last_updated_timestamp": 1719769718,  
    "query_result": null,  
    "space_id": "3c409c00b54a44c79f79da06b82460e2",  
    "status": "IN_PROGRESS",  
    "user_id": 12345  
  }  
}
```

## Step 5: Retrieve generated SQL

Use the `conversation_id` and `message_id` in the response to poll to check the message's generation status and retrieve the generated SQL from Genie. See `GET /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}` for complete request and response details.

**Note**: Only `POST` requests count toward the queries-per-minute throughput limit. `GET` requests used to poll results are not subject to this limit.

Substitute your values into the following request:

```
GET /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}  
HOST= <DATABRICKS_INSTANCE>  
Authorization: Bearer <your_authentication_token>
```

The following example response reports the message details:

```
Response:  
  
{  
  "attachments": null,  
  "content": "Give me top sales for last month",  
  "conversation_id": "6a64adad2e664ee58de08488f986af3e",  
  "created_timestamp": 1719769718,  
  "error": null,  
  "id": "e1ef34712a29169db030324fd0e1df5f",  
  "last_updated_timestamp": 1719769718,  
  "query_result": null,  
  "space_id": "3c409c00b54a44c79f79da06b82460e2",  
  "status": "IN_PROGRESS",  
  "user_id": 12345  
}
```

When the `status` field is `COMPLETED` the response is populated in the `attachments` array.

## Step 6: Retrieve query results

The `attachments` array contains Genie's response. It includes the generated text response (`text`), the query statement if it exists (`query`), and an identifier that you can use to get the associated query results (`attachment_id`). Replace the placeholders in the following example to retrieve the generated query results:

```
GET /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}/query-result/{attachment_id}  
Authorization: Bearer <your_authentication_token>
```

See `GET /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result`.

## Step 7: Ask follow-up questions

After you receive a response, use the `conversation_id` to continue the conversation. Context from previous messages is retained and used in follow-up responses. For complete request and response details, see `POST /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages`.

```
POST /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages  
HOST= <DATABRICKS_INSTANCE>  
Authorization: <your_authentication_token>  
{  
  "content": "Which of these customers opened and forwarded the email?",  
}
```

## Reference and retrieve historical data

The Genie API provides additional endpoints for managing existing conversations and retrieving historical data for analysis.

### Reference old conversation threads

To allow users to refer to old conversation threads, use the List conversation messages endpoint `GET /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}/messages` to retrieve all messages from a specific conversation thread.

### Retrieve conversation data for analysis

Space managers can programmatically retrieve all previous messages asked across all users of a space for analysis. To retrieve this data:

1. Use the `GET /api/2.0/genie/spaces/{space_id}/conversations` endpoint to get all existing conversation threads in a space.
2. For each conversation ID returned, use the `GET /api/2.0/genie/spaces/{space_id}/conversations` endpoint to retrieve the list of messages for that conversation.

## Best practices for using the Genie API

To maintain performance and reliability when using the Genie API:

* **Implement request queuing and backoff:** The API does not manage request retries. Use your own queuing system and implement incremental backoff to avoid exceeding throughput limits.
* **Poll for status updates every 1 to 5 seconds:** Continue polling until a conclusive message status, such as `COMPLETED`, `FAILED`, or `CANCELLED`, is received. Limit polling to 10 minutes for most queries. If there is no conclusive response after 10 minutes, stop polling and return a timeout error or prompt the user to manually check the query status later.
* **Use exponential backoff:** Apply exponential backoff to your polling frequency, increasing the interval between polls up to a maximum of 1 minute. This approach helps reduce latency for faster queries while improving reliability for longer-running queries.
* **Start a new conversation for each session:** Avoid reusing conversation threads across sessions, as this can reduce accuracy due to unintended context reuse.
* **Maintain conversation limits:** To manage old conversations and stay under the 10,000 conversation limit:
  1. Use the `GET /api/2.0/genie/spaces/{space_id}/conversations` endpoint to see all existing conversation threads in a space.
  2. Identify conversations that are no longer needed, such as older conversations or test conversations.
  3. Use the `DELETE /api/2.0/genie/spaces/{space_id}/conversations/{conversation_id}` endpoint to remove conversations programmatically.
* **Be aware of query result limit**: The Genie API returns a maximum of 5,000 rows per query result. If your data analysis requires more rows, consider refining your question to focus on a specific subset of data or use filters to narrow the results.

## Monitor the space

After your application is set up, you can monitor questions and responses in the Databricks UI.

Encourage users to test the space so that you learn about the types of questions they are likely to ask and the responses they receive. Use the **Monitoring** tab to view questions and responses.

You can also use audit logs to monitor activity in a Genie space.

## Throughput limit

During the Public Preview period, the throughput rates for the Genie API free tier are best-effort and depend on system capacity. Under normal or low-traffic conditions, the API limits requests to 5 queries per minute per workspace. During peak usage periods, the system processes requests based on available capacity, which can result in lower throughput.
