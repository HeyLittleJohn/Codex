from collections import namedtuple, deque
import random

import torch
import numpy as np
from pandas import DataFrame
import torch.nn as nn
import torch.nn.functional as F

from rl_agent.utils import dataframe_to_tensor
from rl_agent.constants import (
    GAMMA,
    ALPHA,
    EPSILON,
    HIDDEN_SIZE_LG,
    HIDDEN_SIZE_SM,
    DEVICE,
    SUCCESS_THRESHOLD,
)

transition = namedtuple("tran", ("s", "a", "r", "s_prime", "end"))


class DQN_Network(nn.Module):
    def __init__(self, actions_dim, state_dim):
        super().__init__()
        self.actions_dim = actions_dim
        self.hidden_size_lg = HIDDEN_SIZE_LG  # can tune these
        self.hidden_size_sm = HIDDEN_SIZE_SM
        self.epsilon = EPSILON
        self.alpha = ALPHA
        self.gamma = GAMMA
        self.rewards = []
        self.best = (0, 0)  # (reward, episode)

        # layers
        self.fc1 = nn.Linear(state_dim, self.hidden_size_lg)
        self.fc2 = nn.Linear(self.hidden_size_lg, self.hidden_size_sm)
        self.fc3 = nn.Linear(self.hidden_size_sm, actions_dim)

    def forward(self, x):
        if not type(x) == torch.Tensor:
            x = torch.tensor(x).to(DEVICE)
        x = F.leaky_relu(self.fc1(x))
        x = F.leaky_relu(self.fc2(x))
        x = F.leaky_relu(self.fc3(x))
        # x = torch.sigmoid(self.fc3(x)) # an alternative to leaky_relu
        return x

    def choose_action(self, state: DataFrame, feature_cols: list[str]) -> dict:
        """function to choose an action based on the current state of the environment.
        Maps actions in a dictionary to the considered options ticker

        Args:
            state (DataFrame): current state of the environment
            feature_cols (list[str]): list of feature columns that are model inputs

        Returns:
            actions: (dict[str:int]) actions mapped to affiliated options tickers
                {"O:SPY230616P00368000": 0, "O:SPY230616P00369000": 1, ...}
        """
        actions = {}
        for i in range(state.shape[0]):
            if np.random.rand() <= self.epsilon:
                actions[state.iloc[i]["options_ticker"]] = np.random.randint(self.actions_dim)
            else:
                with torch.no_grad():
                    feature_state = dataframe_to_tensor(state.iloc[i][feature_cols])
                    pred = self.forward(feature_state)
                    actions[state.iloc[i]["options_ticker"]] = torch.argmax(pred).item()  # gets it off the gpu
        return actions

    def decay_epsilon(self):
        if self.epsilon > 0.001:
            self.epsilon *= 0.9

    def gamma_update(self, episode):
        if episode % 20 == 0 and self.gamma < 0.95:  # TODO: update magic number
            self.gamma += 0.05

    def check_progress(self, reward, episode):
        """function to evaluate the reward being earned per episode, compared with recent averages.
        If reward is above a certain threshold, the agent is considered to have solved the environment"""
        done = False
        self.rewards.append(reward)
        if reward > self.best[0]:
            print("new best job! Score:{}, Episode:{}".format(reward, episode))
            self.best = (reward, episode)
        recent = np.mean(self.rewards[-100:])  # moving average of last 100 rewards
        if recent > SUCCESS_THRESHOLD:
            print("Done! Your last 100 episode average was: ", recent)
            done = True
        if episode % 100 == 0:
            print("Episode:{}, recent average:{}".format(episode, recent))
        return done


class Memories(object):
    def __init__(self, memory_max):
        self.replay_memory = deque([], maxlen=memory_max)

    def add_transition(self, obs):
        self.replay_memory.append(obs)

    def sample_memories(self, num):
        return random.sample(self.replay_memory, num)


class test_agent(object):
    pass
