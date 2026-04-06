from typing import Optional, cast

from rcrscore.entities import Building, EntityID, GasStation, Refuge, Road

from adf_core_python.core.agent.communication.message_manager import MessageManager
from adf_core_python.core.agent.develop.develop_data import DevelopData
from adf_core_python.core.agent.info.agent_info import AgentInfo
from adf_core_python.core.agent.info.scenario_info import ScenarioInfo
from adf_core_python.core.agent.info.world_info import WorldInfo
from adf_core_python.core.agent.module.module_manager import ModuleManager
from adf_core_python.core.agent.precompute.precompute_data import PrecomputeData
from adf_core_python.core.component.module.algorithm.path_planning import (
  PathPlanning,
)
from adf_core_python.core.component.module.complex.road_detector import RoadDetector

# 評価計算：重みまとめ
_WEIGHT_DISTANCE = 10.0
_WEIGHT_PRIORITY_ROAD = 0.5

class RoadDetector(RoadDetector):
  def __init__(
    self,
    agent_info: AgentInfo,
    world_info: WorldInfo,
    scenario_info: ScenarioInfo,
    module_manager: ModuleManager,
    develop_data: DevelopData,
  ) -> None:
    super().__init__(
      agent_info, world_info, scenario_info, module_manager, develop_data
    )

    self._path_planning: PathPlanning = cast(
      PathPlanning,
      module_manager.get_module(
        "RoadDetector.PathPlanning",
        "adf_core_python.implement.module.algorithm.a_star_path_planning.AStarPathPlanning",
      ),
    )

    self.register_sub_module(self._path_planning)
    self._result: Optional[EntityID] = None

  def precompute(self, precompute_data: PrecomputeData) -> RoadDetector:
    super().precompute(precompute_data)
    return self

  def resume(self, precompute_data: PrecomputeData) -> RoadDetector:
    super().resume(precompute_data)
    if self.get_count_resume() >= 2:
      return self

    # 建物の周りの道路を全て集める
    self._target_areas: set[EntityID] = set()
    entities = self._world_info.get_entities_of_types([Refuge, Building, GasStation])
    for entity in entities:
      if not isinstance(entity, Building):
        continue
      for entity_id in entity.get_neighbors():
        neighbor = self._world_info.get_entity(entity_id)
        if isinstance(neighbor, Road):
          self._target_areas.add(entity_id)

    # 避難所の周りの道路を全て集める
    self._priority_roads = set()
    for entity in self._world_info.get_entities_of_types([Refuge]):# 避難所だけをentitiesに入れている
      if not isinstance(entity, Building):
        continue
      for entity_id in entity.get_neighbors():
        neighbor = self._world_info.get_entity(entity_id)
        if isinstance(neighbor, Road):
          self._priority_roads.add(entity_id)

    return self

  def prepare(self) -> RoadDetector:
    super().prepare()
    if self.get_count_prepare() >= 2:
      return self

    self._target_areas = set()
    entities = self._world_info.get_entities_of_types([Refuge, Building, GasStation])
    for entity in entities:
      building: Building = cast(Building, entity)
      for entity_id in building.get_neighbors():
        neighbor = self._world_info.get_entity(entity_id)
        if isinstance(neighbor, Road):
          self._target_areas.add(entity_id)

    self._priority_roads = set()
    for entity in self._world_info.get_entities_of_types([Refuge]):
      refuge: Refuge = cast(Refuge, entity)
      for entity_id in refuge.get_neighbors():
        neighbor = self._world_info.get_entity(entity_id)
        if isinstance(neighbor, Road):
          self._priority_roads.add(entity_id)

    return self

  def update_info(self, message_manager: MessageManager) -> RoadDetector:
    super().update_info(message_manager)
    if self.get_count_update_info() >= 2:
      return self

    # 現在のターゲットは存在しているか？
    if self._result is not None:
      # 現在位置はターゲットであるか？
      if self._agent_info.get_position_entity_id() == self._result:#ここ()修正
        entity = self._world_info.get_entity(self._result)
        # ターゲットは建物なら，ターゲットから外す
        if isinstance(entity, Building):
          self._result = None
        # ターゲットが道なら道ならば瓦礫が存在しない場合のみターゲットから外し，かつ候補集合からは除外
        elif isinstance(entity, Road):
          road = entity
          if road.get_blockades() == []:
            self._target_areas.remove(self._result)
            self._result = None

    return self

  def calculate(self) -> RoadDetector:
    # ターゲットは存在しているか
    if self._result is None:
      # 現在地の所得
      position_entity_id = self._agent_info.get_position_entity_id()
      # 現在地の所得確認
      if position_entity_id is None:
        return self
      
      # 現在の位置はターゲット候補に含まれる位置か
      if position_entity_id in self._target_areas:
        # そうならターゲットに設定
        self._result = position_entity_id
        return self
      
      # 優先道路のなかですでに候補道路から外れているものを除去する
      remove_list = []
      for entity_id in self._priority_roads:
        if entity_id not in self._target_areas:
          remove_list.append(entity_id)
      self._priority_roads = self._priority_roads - set(remove_list)

      # # 優先道路候補があるか
      # if len(self._priority_roads) > 0:
      #   # 現在位置の取得
      #   agent_position = self._agent_info.get_position_entity_id()
      #   # 現在位置の取得確認
      #   if agent_position is None:
      #     return self
        
      #   # 候補集合の中から最も近いものをターゲットとして決定
      #   _nearest_target_area = agent_position
      #   _nearest_distance = float("inf")
      #   for target_area in self._target_areas:
      #     if (
      #       self._world_info.get_distance(agent_position, target_area)
      #       < _nearest_distance
      #     ):
      #       _nearest_target_area = target_area
      #       _nearest_distance = self._world_info.get_distance(
      #         agent_position, target_area
      #       )

      #現在位置の取得
      agent_position = self._agent_info.get_position_entity_id()
      # 現在位置の取得確認
      if agent_position is None:
        return self
      
      # 評価値が最大のものをターゲットとして指定
      _highest_target_area = agent_position
      _highest_evaluate = float("-inf")

      for target_area in self._target_areas:
        _evaluate_target_area = self._evaluate(target_area)
        if(_evaluate_target_area > _highest_evaluate):
            _highest_evaluate = _evaluate_target_area
            _highest_target_area = target_area
      self._logger.info(f"targetarea = {_highest_target_area}")
      # 経路探索
      path: list[EntityID] = self._path_planning.get_path(
        agent_position, _highest_target_area
      )
      # 経路が存在するか確認
      if path is not None and len(path) > 0:
        self._result = path[-1]
    
    return self
  
  # 評価値計算
  def _evaluate(self,target_area :EntityID) -> float:
    return (
      self._score_distance(target_area) * _WEIGHT_DISTANCE
      + self._score_priority_road(target_area) * _WEIGHT_PRIORITY_ROAD
    )
  

  # 距離スコア：距離+1の逆数を返す(0除算対策)
  def _score_distance(self,target_area :EntityID) -> float:
    #現在位置の取得
    agent_position = self._agent_info.get_position_entity_id()
    # 現在位置の取得確認
    if agent_position is None:
      return float("-inf")
    
    return  1/(self._world_info.get_distance(agent_position, target_area)+1)
  
  # 優先道路スコア：優先道路に含まれているか
  def _score_priority_road(self,target_area:EntityID) -> float:
    return 1.0 if target_area in self._priority_roads else 0.0

  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result
