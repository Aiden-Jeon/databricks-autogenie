"""Databricks LLM client for calling serving endpoints."""

import json
import re
import os
import base64
import logging
from io import BytesIO
from typing import Dict, Any, Optional, List, Union
import requests
import aiohttp
from pydantic import ValidationError
from PIL import Image

from genie.models import LLMResponse, GenieSpaceConfig

logger = logging.getLogger(__name__)


def _repair_json(text: str) -> str:
    """Attempt to fix common LLM JSON errors before parsing.

    Fixes: trailing commas, single-line // comments, control characters.
    """
    # Remove single-line comments (// ...)
    text = re.sub(r'//[^\n]*', '', text)
    # Remove trailing commas before } or ]
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # Replace control characters (except newline/tab) that break JSON
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text


class DatabricksLLMClient:
    """Client for calling Databricks serving endpoints."""
    
    def __init__(
        self,
        endpoint_name: str,
        databricks_host: Optional[str] = None,
        databricks_token: Optional[str] = None
    ):
        """
        Initialize the Databricks LLM client.
        
        Args:
            endpoint_name: Name of the serving endpoint
            databricks_host: Databricks workspace URL (defaults to DATABRICKS_HOST env var)
            databricks_token: Databricks personal access token (defaults to DATABRICKS_TOKEN env var)
        """
        self.endpoint_name = endpoint_name
        self.databricks_host = databricks_host or os.getenv("DATABRICKS_HOST")
        self.databricks_token = databricks_token or os.getenv("DATABRICKS_TOKEN")
        
        if not self.databricks_host:
            raise ValueError("databricks_host must be provided or DATABRICKS_HOST env var must be set")
        if not self.databricks_token:
            raise ValueError("databricks_token must be provided or DATABRICKS_TOKEN env var must be set")
        
        # Clean up host URL
        self.databricks_host = self.databricks_host.rstrip('/')
        if not self.databricks_host.startswith('http'):
            self.databricks_host = f"https://{self.databricks_host}"
        
        self.endpoint_url = f"{self.databricks_host}/serving-endpoints/{self.endpoint_name}/invocations"
        
    def _make_request(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make a request to the Databricks serving endpoint.
        
        Args:
            prompt: The prompt to send to the model
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature (lower = more deterministic)
            **kwargs: Additional parameters to pass to the model
            
        Returns:
            The raw response from the API
        """
        headers = {
            "Authorization": f"Bearer {self.databricks_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }
        
        response = requests.post(
            self.endpoint_url,
            headers=headers,
            json=payload,
            timeout=300  # 5 minutes timeout
        )
        
        response.raise_for_status()
        return response.json()
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        images: Optional[List[Union[str, Image.Image]]] = None,
        **kwargs
    ) -> str:
        """
        Generate text from the LLM, optionally with images.
        
        Args:
            prompt: The prompt to send to the model
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature
            images: Optional list of images (PIL Image objects or base64 strings)
            **kwargs: Additional parameters
            
        Returns:
            The generated text
        """
        if images:
            response = self._make_multimodal_request(prompt, images, max_tokens, temperature, **kwargs)
        else:
            response = self._make_request(prompt, max_tokens, temperature, **kwargs)
        
        # Extract the generated text from the response
        # Note: The exact structure depends on the serving endpoint format
        # Common formats:
        if "choices" in response:
            # OpenAI-style format
            return response["choices"][0]["message"]["content"]
        elif "predictions" in response:
            # MLflow model format
            return response["predictions"][0]
        elif "outputs" in response:
            # Alternative format
            return response["outputs"][0]
        else:
            # Return the whole response as string if format is unknown
            return str(response)
    
    def _make_multimodal_request(
        self,
        prompt: str,
        images: List[Union[str, Image.Image]],
        max_tokens: int = 4000,
        temperature: float = 0.1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make a multimodal request with text and images.
        
        Args:
            prompt: Text prompt
            images: List of images (PIL Image objects or base64 strings)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters
            
        Returns:
            The raw response from the API
        """
        headers = {
            "Authorization": f"Bearer {self.databricks_token}",
            "Content-Type": "application/json"
        }
        
        # Build content array with text and images
        content = []
        
        # Add text
        content.append({
            "type": "text",
            "text": prompt
        })
        
        # Add images
        for img in images:
            if isinstance(img, str):
                # Already base64 encoded
                image_data = img
            elif isinstance(img, Image.Image):
                # Convert PIL Image to base64
                image_data = self._image_to_base64(img)
            else:
                raise ValueError(f"Unsupported image type: {type(img)}")
            
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_data}"
                }
            })
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }
        
        response = requests.post(
            self.endpoint_url,
            headers=headers,
            json=payload,
            timeout=300  # 5 minutes timeout
        )
        
        response.raise_for_status()
        return response.json()
    
    @staticmethod
    def _image_to_base64(image: Image.Image, format: str = "PNG") -> str:
        """
        Convert PIL Image to base64 string.
        
        Args:
            image: PIL Image object
            format: Image format (PNG, JPEG, etc.)
            
        Returns:
            Base64 encoded image string
        """
        buffered = BytesIO()
        image.save(buffered, format=format)
        img_bytes = buffered.getvalue()
        return base64.b64encode(img_bytes).decode('utf-8')
    
    def generate_structured(
        self,
        prompt: str,
        response_model: type,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        **kwargs
    ):
        """
        Generate structured output from the LLM using a Pydantic model.
        
        Args:
            prompt: The prompt to send to the model
            response_model: Pydantic model class to parse the response into
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters
            
        Returns:
            Instance of response_model with parsed data
            
        Raises:
            ValidationError: If the LLM response doesn't match the expected schema
            json.JSONDecodeError: If the LLM response is not valid JSON
        """
        # Generate the response
        response_text = self.generate(prompt, max_tokens, temperature, **kwargs)
        
        # Try to extract JSON from the response (in case there's extra text)
        response_text = response_text.strip()
        
        # Find JSON object in the response
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError(
                f"No JSON object found in LLM response. Response length: {len(response_text)} chars."
            )
        
        json_text = response_text[start_idx:end_idx + 1]
        
        # Parse JSON
        response_data = json.loads(json_text)
        
        # Validate and parse with Pydantic
        return response_model(**response_data)
    
    def generate_genie_config(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        include_reasoning: bool = True,
        **kwargs
    ) -> LLMResponse:
        """
        Generate a Genie space configuration from the LLM.
        
        Args:
            prompt: The prompt to send to the model
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature
            include_reasoning: Whether to include reasoning in the response
            **kwargs: Additional parameters
            
        Returns:
            LLMResponse object containing the parsed Genie space configuration
            
        Raises:
            ValidationError: If the LLM response doesn't match the expected schema
            json.JSONDecodeError: If the LLM response is not valid JSON
        """
        # Generate the response
        response_text = self.generate(prompt, max_tokens, temperature, **kwargs)
        
        # Try to extract JSON from the response (in case there's extra text)
        response_text = response_text.strip()
        
        # Find JSON object in the response
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError(
                f"No JSON object found in LLM response. Response length: {len(response_text)} chars. "
                f"If using a reasoning model (like GPT-5.2), try increasing max_tokens to 16000+."
            )
        
        json_text = response_text[start_idx:end_idx + 1]
        
        # Parse JSON
        response_data = json.loads(json_text)
        
        # Validate and parse with Pydantic
        if include_reasoning:
            # Response should contain genie_space_config, reasoning, and confidence_score
            return LLMResponse(**response_data)
        else:
            # Response is just the GenieSpaceConfig
            genie_config = GenieSpaceConfig(**response_data)
            return LLMResponse(genie_space_config=genie_config)
    
    async def generate_async(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        images: Optional[List[Union[str, Image.Image]]] = None,
        **kwargs
    ) -> str:
        """
        Async version of generate method.
        
        Args:
            prompt: The prompt to send to the model
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature
            images: Optional list of images (PIL Image objects or base64 strings)
            **kwargs: Additional parameters
            
        Returns:
            The generated text
        """
        if images:
            response = await self._make_multimodal_request_async(prompt, images, max_tokens, temperature, **kwargs)
        else:
            response = await self._make_request_async(prompt, max_tokens, temperature, **kwargs)
        
        # Extract the generated text from the response
        if "choices" in response:
            # OpenAI-style format
            return response["choices"][0]["message"]["content"]
        elif "predictions" in response:
            # MLflow model format
            return response["predictions"][0]
        elif "outputs" in response:
            # Alternative format
            return response["outputs"][0]
        else:
            # Return the whole response as string if format is unknown
            return str(response)
    
    async def _make_request_async(
        self,
        prompt: str,
        max_tokens: int = 4000,
        temperature: float = 0.1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Async version of _make_request.
        
        Args:
            prompt: The prompt to send to the model
            max_tokens: Maximum number of tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters to pass to the model
            
        Returns:
            The raw response from the API
        """
        headers = {
            "Authorization": f"Bearer {self.databricks_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
            ) as response:
                response.raise_for_status()
                return await response.json()
    
    async def _make_multimodal_request_async(
        self,
        prompt: str,
        images: List[Union[str, Image.Image]],
        max_tokens: int = 4000,
        temperature: float = 0.1,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Async version of _make_multimodal_request.
        
        Args:
            prompt: Text prompt
            images: List of images (PIL Image objects or base64 strings)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters
            
        Returns:
            The raw response from the API
        """
        headers = {
            "Authorization": f"Bearer {self.databricks_token}",
            "Content-Type": "application/json"
        }
        
        # Build content array with text and images
        content = []
        
        # Add text
        content.append({
            "type": "text",
            "text": prompt
        })
        
        # Add images
        for img in images:
            if isinstance(img, str):
                # Already base64 encoded
                image_data = img
            elif isinstance(img, Image.Image):
                # Convert PIL Image to base64
                image_data = self._image_to_base64(img)
            else:
                raise ValueError(f"Unsupported image type: {type(img)}")
            
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_data}"
                }
            })
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint_url,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)  # 5 minutes timeout
            ) as response:
                response.raise_for_status()
                return await response.json()


class DatabricksFoundationModelClient(DatabricksLLMClient):
    """Client for calling Databricks Foundation Model APIs."""
    
    def __init__(
        self,
        model_name: str = "databricks-claude-sonnet-4",
        databricks_host: Optional[str] = None,
        databricks_token: Optional[str] = None
    ):
        """
        Initialize client for Databricks Foundation Model API.
        
        Args:
            model_name: Name of the foundation model to use
            databricks_host: Databricks workspace URL
            databricks_token: Databricks personal access token
        """
        # Foundation Model API uses a different endpoint structure
        self.model_name = model_name
        self.databricks_host = databricks_host or os.getenv("DATABRICKS_HOST")
        self.databricks_token = databricks_token or os.getenv("DATABRICKS_TOKEN")
        
        if not self.databricks_host:
            raise ValueError("databricks_host must be provided or DATABRICKS_HOST env var must be set")
        if not self.databricks_token:
            raise ValueError("databricks_token must be provided or DATABRICKS_TOKEN env var must be set")
        
        # Clean up host URL
        self.databricks_host = self.databricks_host.rstrip('/')
        if not self.databricks_host.startswith('http'):
            self.databricks_host = f"https://{self.databricks_host}"
        
        # Foundation Model API endpoint
        self.endpoint_url = f"{self.databricks_host}/serving-endpoints/{self.model_name}/invocations"
        self.endpoint_name = model_name
