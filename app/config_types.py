"""Auto-generated configuration types from YAML schemas."""
from dataclasses import dataclass
from typing import List, Dict
import yaml
import os


@dataclass
class JudgeModel:
    model: str
    description: str
    role: str
    weight: float


@dataclass
class SelectionStrategy:
    judge_1_pool: List[str]
    judge_2_pool: List[str]
    tiebreaker_pool: List[str]
    rotation_algorithm: str


@dataclass
class GroqJudges:
    primary_pool: List[JudgeModel]
    selection_strategy: SelectionStrategy


@dataclass
class MetaEvolution:
    max_tokens: int
    timeout_seconds: int
    judge_scoring_weight: float
    semantic_similarity_weight: float


@dataclass
class OllamaConfig:
    timeout_seconds: int
    max_tokens: int
    default_model: str


@dataclass
class ServerConfig:
    port: int
    cors_origins: List[str]
    rate_limit_per_minute: int
    log_level: str


@dataclass
class FeatureFlags:
    code_loop_enabled: bool
    memory_integration: bool
    rag_tools: bool
    web_search: bool


@dataclass
class PerformanceConfig:
    cache_ttl_seconds: int
    max_memory_entries: int
    embedding_batch_size: int


@dataclass
class SystemConfig:
    meta_evolution: MetaEvolution
    ollama: OllamaConfig
    server: ServerConfig
    feature_flags: FeatureFlags
    performance: PerformanceConfig


def load_models_config() -> GroqJudges:
    """Load judge models configuration from YAML."""
    config_path = os.path.join(os.path.dirname(__file__), "../config/models.yaml")
    
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    groq_judges = data['groq_judges']
    
    # Convert judge models
    primary_pool = [
        JudgeModel(
            model=judge['model'],
            description=judge['description'],
            role=judge['role'],
            weight=judge['weight']
        )
        for judge in groq_judges['primary_pool']
    ]
    
    # Convert selection strategy
    strategy_data = groq_judges['selection_strategy']
    selection_strategy = SelectionStrategy(
        judge_1_pool=strategy_data['judge_1_pool'],
        judge_2_pool=strategy_data['judge_2_pool'],
        tiebreaker_pool=strategy_data['tiebreaker_pool'],
        rotation_algorithm=strategy_data['rotation_algorithm']
    )
    
    return GroqJudges(
        primary_pool=primary_pool,
        selection_strategy=selection_strategy
    )


def load_system_config() -> SystemConfig:
    """Load system configuration from YAML."""
    config_path = os.path.join(os.path.dirname(__file__), "../config/system.yaml")
    
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)
    
    return SystemConfig(
        meta_evolution=MetaEvolution(**data['meta_evolution']),
        ollama=OllamaConfig(**data['ollama']),
        server=ServerConfig(**data['server']),
        feature_flags=FeatureFlags(**data['feature_flags']),
        performance=PerformanceConfig(**data['performance'])
    )


# Singleton instances
_models_config: GroqJudges = None
_system_config: SystemConfig = None


def get_models_config() -> GroqJudges:
    """Get cached models configuration."""
    global _models_config
    if _models_config is None:
        _models_config = load_models_config()
    return _models_config


def get_system_config() -> SystemConfig:
    """Get cached system configuration."""
    global _system_config
    if _system_config is None:
        _system_config = load_system_config()
    return _system_config