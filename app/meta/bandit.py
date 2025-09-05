import random
from typing import List, Dict

class EpsilonGreedy:
    def __init__(self, eps: float = 0.1):
        self.eps = eps

    def select(self, operators: List[str], stats: Dict[str, Dict]) -> str:
        """
        Epsilon-greedy selection of operator.
        
        Args:
            operators: List of available operator names
            stats: Dict of {operator_name: {"n": int, "avg_reward": float}}
            
        Returns:
            Selected operator name
        """
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