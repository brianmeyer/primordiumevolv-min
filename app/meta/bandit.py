import random
import math
from typing import List, Dict

class EpsilonGreedy:
    def __init__(self, eps: float = 0.1):
        self.eps = eps

    def select(self, operators: List[str], stats: Dict[str, Dict]) -> str:
        """
        Epsilon-greedy selection of operator with forced initial exploration.
        
        Args:
            operators: List of available operator names
            stats: Dict of {operator_name: {"n": int, "avg_reward": float}}
            
        Returns:
            Selected operator name
        """
        # Force initial exploration: try untried operators first
        untried_ops = [op for op in operators if op not in stats or stats[op]["n"] == 0]
        if untried_ops:
            return random.choice(untried_ops)
        
        if random.random() < self.eps:
            # Explore: random choice
            return random.choice(operators)
        
        # Exploit: choose best average reward
        best_op = None
        best_reward = float('-inf')
        
        for op in operators:
            if op in stats and stats[op]["n"] > 0:
                reward = stats[op]["avg_reward"]
                if reward > best_reward:
                    best_reward = reward
                    best_op = op
        
        # If no stats yet, random choice
        if best_op is None:
            return random.choice(operators)
            
        return best_op

    def update(self, name: str, reward: float, stats: Dict[str, Dict]) -> Dict[str, Dict]:
        """
        Update stats with new reward observation.
        
        Args:
            name: Operator name
            reward: Observed reward
            stats: Current stats dict
            
        Returns:
            Updated stats dict
        """
        if name not in stats:
            stats[name] = {"n": 0, "avg_reward": 0.0}
        
        current = stats[name]
        n = current["n"]
        avg_reward = current["avg_reward"]
        
        # Update running average
        new_n = n + 1
        new_avg = ((avg_reward * n) + reward) / new_n
        
        stats[name] = {"n": new_n, "avg_reward": new_avg}
        
        return stats


class UCB:
    def __init__(self, c: float = 2.0, warm_start_min_pulls: int = 1, stratified_explore: bool = True):
        """
        Upper Confidence Bound bandit algorithm with warm start and stratified exploration.
        
        Args:
            c: UCB exploration constant (higher = more exploration)
            warm_start_min_pulls: Min pulls per operator before pure UCB
            stratified_explore: Whether to do deterministic first pass
        """
        self.c = c
        self.warm_start_min_pulls = warm_start_min_pulls
        self.stratified_explore = stratified_explore
        self._stratified_order = []
        self._stratified_index = 0
    
    def select(self, operators: List[str], stats: Dict[str, Dict]) -> str:
        """
        UCB selection with warm start and stratified exploration.
        
        Args:
            operators: List of available operator names
            stats: Dict of {operator_name: {"n": int, "avg_reward": float, "mean_payoff": float}}
            
        Returns:
            Selected operator name
        """
        # Initialize stratified order on first call
        if self.stratified_explore and not self._stratified_order:
            self._stratified_order = operators.copy()
            random.shuffle(self._stratified_order)
            self._stratified_index = 0
        
        # Stratified exploration: deterministic first pass
        if (self.stratified_explore and 
            self._stratified_index < len(self._stratified_order)):
            selected = self._stratified_order[self._stratified_index]
            self._stratified_index += 1
            return selected
        
        # Warm start: ensure min pulls before pure UCB
        under_min_ops = [op for op in operators 
                        if op not in stats or stats[op]["n"] < self.warm_start_min_pulls]
        if under_min_ops:
            return random.choice(under_min_ops)
        
        # Pure UCB selection
        total_n = sum(stats[op]["n"] for op in operators if op in stats)
        
        if total_n == 0:
            return random.choice(operators)
        
        best_op = None
        best_ucb = float('-inf')
        
        for op in operators:
            if op in stats and stats[op]["n"] > 0:
                n_i = stats[op]["n"]
                mean_payoff = stats[op].get("mean_payoff", stats[op]["avg_reward"])
                
                # UCB1 formula: mean_payoff + c * sqrt(ln(total_n) / n_i)
                confidence_interval = self.c * math.sqrt(math.log(total_n) / n_i)
                ucb_value = mean_payoff + confidence_interval
                
                if ucb_value > best_ucb:
                    best_ucb = ucb_value
                    best_op = op
        
        return best_op if best_op else random.choice(operators)
    
    def update(self, name: str, reward: float, stats: Dict[str, Dict]) -> Dict[str, Dict]:
        """
        Update stats with new reward observation.
        
        Args:
            name: Operator name
            reward: Total reward (outcome + process - cost)
            stats: Current stats dict
            
        Returns:
            Updated stats dict with mean_payoff tracking
        """
        if name not in stats:
            stats[name] = {"n": 0, "avg_reward": 0.0, "mean_payoff": 0.0}
        
        current = stats[name]
        n = current["n"]
        avg_reward = current.get("avg_reward", 0.0)
        mean_payoff = current.get("mean_payoff", 0.0)
        
        # Update running averages
        new_n = n + 1
        new_avg = ((avg_reward * n) + reward) / new_n
        new_mean_payoff = ((mean_payoff * n) + reward) / new_n
        
        stats[name] = {
            "n": new_n, 
            "avg_reward": new_avg,  # Preserve for backward compatibility
            "mean_payoff": new_mean_payoff  # Primary signal for UCB
        }
        
        return stats
        
    def get_ucb_scores(self, operators: List[str], stats: Dict[str, Dict]) -> Dict[str, float]:
        """
        Get current UCB scores for diagnostics.
        
        Returns:
            Dict of {operator: ucb_score} for debugging
        """
        total_n = sum(stats[op]["n"] for op in operators if op in stats)
        ucb_scores = {}
        
        for op in operators:
            if op in stats and stats[op]["n"] > 0:
                n_i = stats[op]["n"]
                mean_payoff = stats[op].get("mean_payoff", stats[op]["avg_reward"])
                confidence_interval = self.c * math.sqrt(math.log(total_n) / n_i)
                ucb_scores[op] = mean_payoff + confidence_interval
            else:
                ucb_scores[op] = float('inf')  # Untried operators get max score
                
        return ucb_scores