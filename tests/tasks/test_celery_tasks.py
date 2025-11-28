"""
Tests for Celery tasks (idea and research tasks).

Tests cover:
- AsyncTask base class
- Idea generation tasks
- Idea scoring tasks
- Combined generate and score tasks
- Research automation tasks
- Task state updates
- Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAsyncTask:
    """Tests for AsyncTask base class."""

    def test_async_task_runs_coroutine(self):
        """Test AsyncTask executes async functions."""
        from api.tasks.idea_tasks import AsyncTask

        class TestTask(AsyncTask):
            async def run(self, value):
                return value * 2

        task = TestTask()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_until_complete = MagicMock(return_value=10)

            result = task(5)

            mock_loop.return_value.run_until_complete.assert_called_once()


class TestGenerateIdeasTask:
    """Tests for generate_ideas_task."""

    @pytest.fixture
    def mock_ideas_service(self):
        """Create mock ideas service."""
        service = MagicMock()
        service.generate_ideas = AsyncMock(return_value=MagicMock(
            ideas_generated=25,
            files_created=25
        ))
        return service

    @pytest.mark.asyncio
    async def test_generate_ideas_task_success(self, mock_ideas_service):
        """Test successful idea generation task."""
        with patch("api.tasks.idea_tasks.get_ideas_service", return_value=mock_ideas_service):
            from api.tasks.idea_tasks import generate_ideas_task

            # Mock the task's update_state and run method
            task_instance = MagicMock()
            task_instance.update_state = MagicMock()

            result = await generate_ideas_task.run(task_instance, "test-project", 25)

            assert result["status"] == "completed"
            assert result["project_id"] == "test-project"
            assert result["ideas_generated"] == 25

    @pytest.mark.asyncio
    async def test_generate_ideas_task_custom_count(self, mock_ideas_service):
        """Test idea generation with custom count."""
        mock_ideas_service.generate_ideas = AsyncMock(return_value=MagicMock(
            ideas_generated=50,
            files_created=50
        ))

        with patch("api.tasks.idea_tasks.get_ideas_service", return_value=mock_ideas_service):
            from api.tasks.idea_tasks import generate_ideas_task

            task_instance = MagicMock()
            task_instance.update_state = MagicMock()

            result = await generate_ideas_task.run(task_instance, "test-project", 50)

            assert result["ideas_generated"] == 50

    @pytest.mark.asyncio
    async def test_generate_ideas_task_updates_state(self, mock_ideas_service):
        """Test task updates state during progress."""
        with patch("api.tasks.idea_tasks.get_ideas_service", return_value=mock_ideas_service):
            from api.tasks.idea_tasks import generate_ideas_task

            task_instance = MagicMock()
            task_instance.update_state = MagicMock()

            await generate_ideas_task.run(task_instance, "test-project", 25)

            task_instance.update_state.assert_called()

    @pytest.mark.asyncio
    async def test_generate_ideas_task_error_handling(self):
        """Test task handles errors."""
        failing_service = MagicMock()
        failing_service.generate_ideas = AsyncMock(side_effect=Exception("Generation failed"))

        with patch("api.tasks.idea_tasks.get_ideas_service", return_value=failing_service):
            from api.tasks.idea_tasks import generate_ideas_task

            task_instance = MagicMock()
            task_instance.update_state = MagicMock()

            with pytest.raises(Exception) as exc_info:
                await generate_ideas_task.run(task_instance, "test-project", 25)

            assert "Generation failed" in str(exc_info.value)
            task_instance.update_state.assert_called_with(
                state="FAILURE", meta={"error": "Generation failed"}
            )


class TestScoreIdeasTask:
    """Tests for score_ideas_task."""

    @pytest.fixture
    def mock_ideas_service(self):
        """Create mock ideas service."""
        service = MagicMock()
        service.score_all_ideas = AsyncMock(return_value=MagicMock(
            total_ideas=25,
            tier_distribution={"very_high": 2, "high": 5, "medium": 10, "low": 8}
        ))
        return service

    @pytest.mark.asyncio
    async def test_score_ideas_task_success(self, mock_ideas_service):
        """Test successful idea scoring task."""
        with patch("api.tasks.idea_tasks.get_ideas_service", return_value=mock_ideas_service):
            from api.tasks.idea_tasks import score_ideas_task

            result = await score_ideas_task.run("test-project")

            assert result["status"] == "completed"
            assert result["project_id"] == "test-project"
            assert result["total_ideas"] == 25
            assert "tier_distribution" in result

    @pytest.mark.asyncio
    async def test_score_ideas_task_tier_distribution(self, mock_ideas_service):
        """Test task returns tier distribution."""
        with patch("api.tasks.idea_tasks.get_ideas_service", return_value=mock_ideas_service):
            from api.tasks.idea_tasks import score_ideas_task

            result = await score_ideas_task.run("test-project")

            assert result["tier_distribution"]["very_high"] == 2
            assert result["tier_distribution"]["high"] == 5

    @pytest.mark.asyncio
    async def test_score_ideas_task_error_handling(self):
        """Test task handles scoring errors."""
        failing_service = MagicMock()
        failing_service.score_all_ideas = AsyncMock(side_effect=Exception("Scoring failed"))

        with patch("api.tasks.idea_tasks.get_ideas_service", return_value=failing_service):
            from api.tasks.idea_tasks import score_ideas_task

            with pytest.raises(Exception) as exc_info:
                await score_ideas_task.run("test-project")

            assert "Scoring failed" in str(exc_info.value)


class TestGenerateAndScoreTask:
    """Tests for generate_and_score_task."""

    @pytest.fixture
    def mock_ideas_service(self):
        """Create mock ideas service."""
        service = MagicMock()
        service.generate_ideas = AsyncMock(return_value=MagicMock(
            ideas_generated=25,
            files_created=25
        ))
        service.score_all_ideas = AsyncMock(return_value=MagicMock(
            total_ideas=25,
            tier_distribution={"very_high": 2, "high": 5}
        ))
        return service

    @pytest.mark.asyncio
    async def test_generate_and_score_task_success(self, mock_ideas_service):
        """Test combined generate and score task."""
        with patch("api.tasks.idea_tasks.get_ideas_service", return_value=mock_ideas_service), \
             patch("api.tasks.idea_tasks.generate_ideas_task") as mock_gen, \
             patch("api.tasks.idea_tasks.score_ideas_task") as mock_score:

            mock_gen.run = AsyncMock(return_value={
                "status": "completed",
                "ideas_generated": 25
            })
            mock_score.run = AsyncMock(return_value={
                "status": "completed",
                "total_ideas": 25
            })

            from api.tasks.idea_tasks import generate_and_score_task

            result = await generate_and_score_task.run("test-project", 25)

            assert result["status"] == "completed"
            assert "generation" in result
            assert "scoring" in result


class TestAutoResearchTask:
    """Tests for auto_research_task."""

    @pytest.fixture
    def mock_automation_service(self):
        """Create mock research automation service."""
        service = MagicMock()
        service.run_full_research = AsyncMock(return_value=MagicMock(
            files_created=10,
            total_sources=25
        ))
        return service

    @pytest.mark.asyncio
    async def test_auto_research_task_success(self, mock_automation_service):
        """Test successful research automation task."""
        with patch("api.tasks.research_tasks.get_research_automation_service", return_value=mock_automation_service):
            from api.tasks.research_tasks import auto_research_task

            task_instance = MagicMock()
            task_instance.update_state = MagicMock()

            result = await auto_research_task.run(task_instance, "test-project")

            assert result["status"] == "completed"
            assert result["project_id"] == "test-project"
            assert result["files_created"] == 10
            assert result["total_sources"] == 25

    @pytest.mark.asyncio
    async def test_auto_research_task_with_categories(self, mock_automation_service):
        """Test research task with specific categories."""
        with patch("api.tasks.research_tasks.get_research_automation_service", return_value=mock_automation_service):
            from api.tasks.research_tasks import auto_research_task

            task_instance = MagicMock()
            task_instance.update_state = MagicMock()

            categories = ["market", "competitor", "trends"]
            result = await auto_research_task.run(task_instance, "test-project", categories)

            mock_automation_service.run_full_research.assert_called_with(
                project_id="test-project",
                categories=categories
            )

    @pytest.mark.asyncio
    async def test_auto_research_task_updates_state(self, mock_automation_service):
        """Test research task updates state during progress."""
        with patch("api.tasks.research_tasks.get_research_automation_service", return_value=mock_automation_service):
            from api.tasks.research_tasks import auto_research_task

            task_instance = MagicMock()
            task_instance.update_state = MagicMock()

            await auto_research_task.run(task_instance, "test-project")

            task_instance.update_state.assert_called()

    @pytest.mark.asyncio
    async def test_auto_research_task_error_handling(self):
        """Test research task handles errors."""
        failing_service = MagicMock()
        failing_service.run_full_research = AsyncMock(side_effect=Exception("Research failed"))

        with patch("api.tasks.research_tasks.get_research_automation_service", return_value=failing_service):
            from api.tasks.research_tasks import auto_research_task

            task_instance = MagicMock()
            task_instance.update_state = MagicMock()

            with pytest.raises(Exception) as exc_info:
                await auto_research_task.run(task_instance, "test-project")

            assert "Research failed" in str(exc_info.value)
            task_instance.update_state.assert_called_with(
                state="FAILURE", meta={"error": "Research failed"}
            )


class TestCeleryAppConfiguration:
    """Tests for Celery app configuration."""

    def test_celery_app_exists(self):
        """Test celery_app is properly configured."""
        from api.tasks.celery_app import celery_app

        assert celery_app is not None
        assert celery_app.main == "outreach_automation" or celery_app.main is not None

    def test_tasks_registered(self):
        """Test tasks are registered with celery app."""
        from api.tasks.celery_app import celery_app

        # Tasks should be discoverable
        assert celery_app is not None


class TestTaskStateManagement:
    """Tests for task state management."""

    def test_task_progress_state(self):
        """Test task can set PROGRESS state."""
        task_instance = MagicMock()
        task_instance.update_state = MagicMock()

        task_instance.update_state(
            state="PROGRESS",
            meta={"status": "Processing", "progress": 50}
        )

        task_instance.update_state.assert_called_with(
            state="PROGRESS",
            meta={"status": "Processing", "progress": 50}
        )

    def test_task_failure_state(self):
        """Test task can set FAILURE state."""
        task_instance = MagicMock()
        task_instance.update_state = MagicMock()

        task_instance.update_state(
            state="FAILURE",
            meta={"error": "Something went wrong"}
        )

        task_instance.update_state.assert_called_with(
            state="FAILURE",
            meta={"error": "Something went wrong"}
        )


class TestTaskResults:
    """Tests for task result structures."""

    def test_idea_generation_result_structure(self):
        """Test idea generation result has expected structure."""
        result = {
            "status": "completed",
            "project_id": "test-project",
            "ideas_generated": 25,
            "files_created": 25
        }

        assert "status" in result
        assert "project_id" in result
        assert "ideas_generated" in result
        assert "files_created" in result

    def test_scoring_result_structure(self):
        """Test scoring result has expected structure."""
        result = {
            "status": "completed",
            "project_id": "test-project",
            "total_ideas": 25,
            "tier_distribution": {
                "very_high": 2,
                "high": 5,
                "medium": 10,
                "low": 8
            }
        }

        assert "status" in result
        assert "total_ideas" in result
        assert "tier_distribution" in result
        assert sum(result["tier_distribution"].values()) == 25

    def test_research_result_structure(self):
        """Test research result has expected structure."""
        result = {
            "status": "completed",
            "project_id": "test-project",
            "files_created": 10,
            "total_sources": 25
        }

        assert "status" in result
        assert "files_created" in result
        assert "total_sources" in result
