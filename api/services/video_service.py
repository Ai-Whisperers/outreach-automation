"""
Video Service

Handles generation of video prompts and videos using Google's Veo 3 model.
"""

import os
import json
import base64
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from google.oauth2 import service_account
from google.cloud import aiplatform
from google.cloud.aiplatform_v1beta1.services.prediction_service import PredictionServiceClient
from google.cloud.aiplatform_v1beta1.types import PredictRequest
from google.protobuf import struct_pb2

from ..config import get_project_config
from ..logging_config import get_logger
from .file_operations import get_file_service
from .ai_client import get_ai_manager
from .ideas_service import get_ideas_service

logger = get_logger("video_service")


class VideoService:
    """
    Service for generating video prompts and videos using Veo 3.
    """

    def __init__(self):
        self.config = get_project_config()
        self.files = get_file_service()
        self.ai = get_ai_manager()
        self.ideas = get_ideas_service()

    async def generate_video_prompts(self, project_id: str) -> List[str]:
        """
        Generate detailed Veo 3 prompts for all ideas with video content.
        
        Args:
            project_id: Project identifier
            
        Returns:
            List of generated prompt file paths
        """
        logger.info(f"Generating video prompts for project: {project_id}")
        
        # Get all ideas
        idea_files = self.files.get_idea_files(project_id)
        generated_files = []
        
        for idea_file in idea_files:
            try:
                # Read idea content
                content = await self.files.read_file(project_id, idea_file)
                
                # Check if video content already exists
                if "## Contenido de Video (Veo 3)" in content:
                    continue

                # Parse basic idea info (simplified parsing)
                title = "Untitled"
                lines = content.split('\n')
                for line in lines:
                    if line.startswith('# '):
                        title = line.replace('# ', '').strip()
                        break
                            
                # Check for video content in the markdown
                has_video = (
                    "Format: Video" in content or 
                    "Format: Reel" in content or 
                    "Format: TikTok" in content or
                    "### Video" in content or
                    "## Video" in content
                )
                
                if not has_video:
                    continue
                    
                # Generate prompt using AI
                prompt_content = await self._generate_single_prompt(title, content)
                
                # Save prompt
                if prompt_content:
                    filename = f"veo3/prompt-{title.lower().replace(' ', '-')[:30]}.md"
                    file_path = await self.files.write_file(project_id, filename, prompt_content)
                    generated_files.append(str(file_path))
                    
                    logger.info(f"Generated video prompt for: {title}")
                    
                    # Append to idea file
                    new_content = content + "\n\n" + prompt_content
                    await self.files.write_file(project_id, idea_file, new_content)
                
            except Exception as e:
                logger.error(f"Failed to generate prompt for {idea_file}: {e}")
                continue
                
        return generated_files

    async def _generate_single_prompt(self, title: str, idea_content: str) -> str:
        """Generate a single Veo 3 prompt using AI."""
        system_prompt = """Eres un experto en generación de prompts para Veo 3, el generador de video de Google DeepMind.
Tu trabajo es crear prompts detallados y optimizados para generar videos publicitarios de alta calidad.
Conoces las mejores prácticas para Veo 3:
- Descripciones visuales específicas y cinematográficas
- Dirección de cámara clara (planos, movimientos, ángulos)
- Iluminación y paleta de colores
- Estilo visual y referencias
- Timing y ritmo del video
- Transiciones entre escenas"""

        user_prompt = f"""Genera un prompt detallado para Veo 3 basado en esta idea:

{idea_content}

Genera un documento con:
## Contenido de Video (Veo 3)

### 1. Prompt Principal para Veo 3
(Un prompt completo y detallado de 100-200 palabras en INGLÉS)

### 2. Especificaciones Técnicas
- Aspect ratio
- Estilo visual
- Paleta de colores

### 3. Variaciones
- 3 variaciones del prompt principal"""

        return await self.ai.generate(
            prompt=user_prompt,
            system=system_prompt,
            temperature=0.7
        )

    async def generate_videos(self, project_id: str) -> List[str]:
        """
        Generate videos from existing prompts using Veo 3 API.
        
        Args:
            project_id: Project identifier
            
        Returns:
            List of generated video file paths
        """
        logger.info(f"Generating videos for project: {project_id}")
        
        # Check configuration
        veo_config = self.config.veo3
        if not veo_config.get("enabled", False):
            logger.warning("Veo 3 generation is disabled in config")
            return []
            
        # Initialize Vertex AI
        try:
            self._init_vertex_ai(veo_config)
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {e}")
            return []
            
        # Get prompt files
        prompt_files = self.files.list_files(project_id, "veo3")
        generated_videos = []
        
        for prompt_file in prompt_files:
            if not prompt_file.endswith(".md") or "prompt-" not in prompt_file:
                continue
                
            try:
                content = await self.files.read_file(project_id, prompt_file)
                
                # Extract main prompt
                main_prompt = self._extract_main_prompt(content)
                if not main_prompt:
                    logger.warning(f"No main prompt found in {prompt_file}")
                    continue
                    
                # Generate video
                video_bytes = await self._call_veo_api(
                    prompt=main_prompt,
                    project_id=veo_config.get("project_id"),
                    location=veo_config.get("location", "us-central1"),
                    model=veo_config.get("model", "veo-3.0-generate-preview")
                )
                
                if video_bytes:
                    # Save video
                    filename = prompt_file.replace("prompt-", "video-").replace(".md", ".mp4")
                    # We need to write bytes, file service handles strings mostly
                    # So we'll use direct file write for binary
                    full_path = self.files.get_project_path(project_id) / filename
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(full_path, "wb") as f:
                        f.write(video_bytes)
                        
                    generated_videos.append(str(full_path))
                    logger.info(f"Generated video: {filename}")
                    
            except Exception as e:
                logger.error(f"Failed to generate video for {prompt_file}: {e}")
                continue
                
        return generated_videos

    def _init_vertex_ai(self, config: Dict):
        """Initialize Vertex AI SDK."""
        project_id = config.get("project_id") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = config.get("location", "us-central1")
        
        credentials = None
        service_account_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        
        if service_account_json:
            info = json.loads(service_account_json)
            credentials = service_account.Credentials.from_service_account_info(info)
            
        aiplatform.init(project=project_id, location=location, credentials=credentials)

    def _extract_main_prompt(self, content: str) -> Optional[str]:
        """Extract the main prompt from the markdown content."""
        lines = content.split('\n')
        in_prompt = False
        prompt = []
        
        for line in lines:
            if "Prompt Principal" in line or "Main Prompt" in line:
                in_prompt = True
                continue
            elif line.startswith("##") and in_prompt:
                in_prompt = False
            
            if in_prompt and line.strip():
                prompt.append(line.strip())
                
        return " ".join(prompt) if prompt else None

    async def _call_veo_api(self, prompt: str, project_id: str, location: str, model: str) -> Optional[bytes]:
        """Call the Veo 3 API via Vertex AI."""
        # This is a simplified implementation wrapping the gRPC call
        # In a real implementation, we would use the proper async client
        
        endpoint = f"projects/{project_id}/locations/{location}/publishers/google/models/{model}"
        client_options = {"api_endpoint": f"{location}-aiplatform.googleapis.com"}
        
        client = PredictionServiceClient(client_options=client_options)
        
        instance = struct_pb2.Struct()
        instance.fields["prompt"].string_value = prompt
        
        parameters = struct_pb2.Struct()
        parameters.fields["aspectRatio"].string_value = "16:9"
        parameters.fields["durationSeconds"].number_value = 6
        
        request = PredictRequest(
            endpoint=endpoint,
            instances=[instance],
            parameters=parameters
        )
        
        # Run in executor to avoid blocking async loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, client.predict, request)
        
        if response.predictions:
            pred_dict = dict(response.predictions[0].struct_value.fields)
            if 'video' in pred_dict:
                return base64.b64decode(pred_dict['video'].string_value)
            elif 'bytesBase64Encoded' in pred_dict:
                return base64.b64decode(pred_dict['bytesBase64Encoded'].string_value)
                
        return None


_video_service: Optional[VideoService] = None

def get_video_service() -> VideoService:
    """Get singleton video service."""
    global _video_service
    if _video_service is None:
        _video_service = VideoService()
    return _video_service
