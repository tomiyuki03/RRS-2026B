from typing import Optional, cast

from rcrscore.entities import Building, EntityID, Refuge, Road

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
    entities = self._world_info.get_entities_of_types([Refuge, Building])
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
    entities = self._world_info.get_entities_of_types([Refuge, Building])
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
        if isinstance(entity, Building):
          self._result = None
        elif isinstance(entity, Road):
          road = entity
          if road.get_blockades() == []:
            self._target_areas.remove(self._result)
            self._result = None

    return self



#修正前 if 優先道路が１本でも残ってる:
#         全候補の中から近いものを選ぶ

#修正後 if 優先道路が残っている:
#         優先道路の中から近いものを選ぶ
#       else:
#          全候補の中から近いものを選ぶ


  def calculate(self) -> RoadDetector:
    # 現在位置を取得
    if self._result is None:
      position_entity_id = self._agent_info.get_position_entity_id()
      if position_entity_id is None:
        return self
      
      # 今いる場所が対象道路なら，まずそこを目標にする
      if position_entity_id in self._target_areas:
        self._result = position_entity_id
        return self
      
      # priority_roads の中に，すでに target_areas から外れた道路があれば削除する
      remove_list = []
      for entity_id in self._priority_roads:
        if entity_id not in self._target_areas:
          remove_list.append(entity_id)

      self._priority_roads = self._priority_roads - set(remove_list)

      agent_position = self._agent_info.get_position_entity_id()
      if agent_position is None:
            return self

      target_candidates = set()

      # まずは避難所周辺道路を最優先で使う
      if len(self._priority_roads) > 0:
            target_candidates = self._priority_roads
      else:
            target_candidates = self._target_areas
        
      # 候補がなければ終了
      if len(target_candidates) == 0:
          return self  
      

      # 候補の中から最も近い道路を選ぶ
      nearest_target_area = None
      nearest_distance = float("inf")

      for target_area in target_candidates:
          distance = self._world_info.get_distance(agent_position, target_area)
          if distance < nearest_distance:
              nearest_target_area = target_area
              nearest_distance = distance

      # 経路が取れた場合のみ目標に設定する
      if nearest_target_area is not None:
          path: list[EntityID] = self._path_planning.get_path(
              agent_position, nearest_target_area
          )
          if path is not None and len(path) > 0:
              self._result = path[-1]

    return self

  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result
