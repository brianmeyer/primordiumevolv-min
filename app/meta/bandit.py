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
    def __init__(self, c: float = 1.41):
        """
        Upper Confidence Bound bandit algorithm.
        
        Args:
            c: Exploration parameter (typically sqrt(2) ≈ 1.41)
        """
        self.c = c
    
    def select(self, operators: List[str], stats: Dict[str, Dict]) -> str:
        """
        UCB selection of operator.
        
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
        
        # Calculate total number of trials
        total_n = sum(stats[op]["n"] for op in operators if op in stats)
        
        if total_n == 0:
            return random.choice(operators)
        
        # Calculate UCB values for each operator
        best_op = None
        best_ucb = float('-inf')
        
        for op in operators:
            if op in stats and stats[op]["n"] > 0:
                n_i = stats[op]["n"]
                avg_reward = stats[op]["avg_reward"]
                
                # UCB formula: avg_reward + c * sqrt(ln(total_n) / n_i)
                confidence_interval = self.c * math.sqrt(math.log(total_n) / n_i)
                ucb_value = avg_reward + confidence_interval
                
                if ucb_value > best_ucb:
                    best_ucb = ucb_value
                    best_op = op
        
        return best_op if best_op else random.choice(operators)
    
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