from typing import Optional, cast

from rcrscore.entities import Building, Entity, EntityID, Refuge,Civilian

from adf_core_python.core.agent.communication.message_manager import MessageManager
from adf_core_python.core.agent.develop.develop_data import DevelopData
from adf_core_python.core.agent.info.agent_info import AgentInfo
from adf_core_python.core.agent.info.scenario_info import ScenarioInfo
from adf_core_python.core.agent.info.world_info import WorldInfo
from adf_core_python.core.agent.module.module_manager import ModuleManager
from adf_core_python.core.component.module.algorithm.clustering import Clustering
from adf_core_python.core.component.module.algorithm.path_planning import PathPlanning
from adf_core_python.core.component.module.complex.search import Search
from adf_core_python.core.logger.logger import get_agent_logger


class SearchB(Search):
  #情報の更新
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

    #調査が終わっていない建物のIDリスト
    self._unreached_building_ids: set[EntityID] = set()
    #目的地の決定
    self._result: Optional[EntityID] = None
    #市民がいた建物のIDリスト
    self._found_civilian_ids: set[EntityID] = set()
    #逆に誰もいなかった建物のIDリスト
    self._empty_building_ids: set[EntityID] = set()

    self._search_round:int  = 0

#サブモジュールの取得
    #クラスタリング
    self._clustering: Clustering = cast(
      Clustering,
      module_manager.get_module(
        "Search.Clustering",
        "adf_core_python.implement.module.algorithm.k_means_clustering.KMeansClustering",
      ),
    )
    #経路探索
    self._path_planning: PathPlanning = cast(
      PathPlanning,
      module_manager.get_module(
        "Search.PathPlanning",
        "adf_core_python.implement.module.algorithm.a_star_path_planning.AStarPathPlanning",
      ),
    )
    #ログの設定
    self._logger = get_agent_logger(
      f"{self.__class__.__module__}.{self.__class__.__qualname__}",
      self._agent_info,
    )

    self.register_sub_module(self._clustering)
    self.register_sub_module(self._path_planning)

  def update_info(self, message_manager: MessageManager) -> Search:
    super().update_info(message_manager)
    if self.get_count_update_info() > 1:
      return self
    
    #現在地の確認とリストの更新
    searched_building_id = self._agent_info.get_position_entity_id()
    #建物の中にいる場合、その建物を探索済みにする
    if searched_building_id is not None:
      self._unreached_building_ids.discard(searched_building_id)
      self._found_civilian_ids.discard(searched_building_id)
      self._empty_building_ids.add(searched_building_id)
    
    changed_entities = self._world_info.get_change_set()
    if changed_entities:
      for entity_id in changed_entities.get_changed_entities():
        entity = self._world_info.get_entity(entity_id)
        if isinstance(entity, Civilian) :
          # 市民(生きてる)のいる場所（建物ID）を記録
          loc_id = entity.get_position()
          if entity.get_hp() >= 10 and isinstance(self._world_info.get_entity(loc_id), Building) and not isinstance(self._world_info.get_entity(loc_id), Refuge):
            self._found_civilian_ids.add(loc_id)
            self._empty_building_ids.discard(loc_id)
            self._logger.debug(
              f"[{self._agent_info.get_time()}]empty_building: {[str(id) for id in self._empty_building_ids]}"
            ) 



    #探索リストが空になった場合、再取得
    if len(self._unreached_building_ids) == 0:
      # if len(self._found_civilian_ids) > 2:
      #   self._unreached_building_ids = set(self._found_civilian_ids)
      #   self._logger.debug(
      #     f"fonund_civilian: {[str(id) for id in self._found_civilian_ids]}"
      #   )
      # else:
      my_cluster_area = self._get_search_targets(area_all=False)
      if len(my_cluster_area) == 0:
        self._unreached_building_ids = self._get_search_targets(area_all=True)
      else:
        self._unreached_building_ids = my_cluster_area
      self._logger.debug(
        f"[{self._agent_info.get_time()}]unreached_building_ids: {len(self._unreached_building_ids)}"
      )


    #self._update_unreached_buildings()

    return self

  def calculate(self) -> Search:
    self._logger.debug(
      f"[{self._agent_info.get_time()}]search calculate"
    )

    #現時点で一番近い建物のIDと距離の変数を初期化
    target_building_id: Optional[EntityID] = None
    target_score: Optional[float] = None

    #自身のクラスタIDを取得
    cluster_index: int = self._clustering.get_cluster_index(
      self._agent_info.get_entity_id()
    )

    #行ってない建物を調べる
    for building_id in self._unreached_building_ids:

      #現在地から建物までの直線距離を取得
      distance = self._world_info.get_distance(
        self._agent_info.get_entity_id(), building_id
      )
      #seed = (building_id.get_value() + self._agent_info.get_entity_id().get_value()) % 100
      #random_bonus = seed * 0.1
      score = 10000 / (distance + 1) # + random_bonus

      #建物が自分のクラスタと同じだった場合重みをプラス
      if self._clustering.get_cluster_index(building_id) == cluster_index:
        score += 500  # 100は仮定値

      if building_id in self._found_civilian_ids :#and self._search_round != 1:
        score += 2000
        self._logger.debug(
          f"[{self._agent_info.get_time()}]building_ids: {building_id}"
        )
      
      #scoreが大きいものにターゲットを更新
      if target_score is None or target_score < score:
        target_building_id = building_id
        target_score = score

    self._result = target_building_id
    return self
  
  # def calculate(self) -> Search:
  #   #現時点で一番近い建物のIDと距離の変数を初期化
  #   nearest_building_id: Optional[EntityID] = None
  #   nearest_distance: Optional[float] = None

  #   #行ってない建物を調べる
  #   for building_id in self._unreached_building_ids:
  #     distance = self._world_info.get_distance(
  #       self._agent_info.get_entity_id(), building_id
  #     )

  #     #一番近ければ変数を更新
  #     if nearest_distance is None or distance < nearest_distance:
  #       nearest_building_id = building_id
  #       nearest_distance = distance
  #   self._result = nearest_building_id
  #   return self

  #決定したIDを渡す
  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result

  #ターゲットになる建物のリストをつくる
  def _get_search_targets(self,area_all:bool = False) -> set[EntityID]:
    if area_all:
      buildings = self._world_info.get_entities_of_types([Building])
    else:
      #自分の担当クラスタの特定
      cluster_index: int = self._clustering.get_cluster_index(
        self._agent_info.get_entity_id()
      )
      #クラスタ内のエンティティを取得
      buildings: list[Entity] = self._clustering.get_cluster_entities(
        cluster_index
      )

    building_entity_ids: list[EntityID] = []
    for entity in buildings:
      if isinstance(entity, Building) and not isinstance(entity, Refuge):
        entity_id = entity.get_entity_id()
        if entity_id not in self._empty_building_ids:
          building_entity_ids.append(entity_id)

    return set(building_entity_ids)

  def _update_unreached_buildings(self) -> None:
    changed_entities = self._world_info.get_change_set()
    visible_buildings = [
      entity_id
      for entity_id in changed_entities.get_changed_entities()
      if isinstance(self._world_info.get_entity(entity_id), Building)
    ]

    for building_id in visible_buildings:
      building = self._world_info.get_entity(building_id)
      if isinstance(building, Building):
        brokenness = building.get_brokenness()
      if brokenness <= 0:
        self._unreached_building_ids.discard(building_id)
