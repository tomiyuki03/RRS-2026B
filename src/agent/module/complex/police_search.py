from typing import Optional, cast

from rcrscore.entities import Building, Entity, EntityID, Refuge, Road, PoliceForce

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


class PoliceSearch(Search):
  # 情報の更新
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

    # 調査が終わっていない建物のIDリスト
    self._unreached_road_ids: set[EntityID] = set()
    # 目的地の決定
    self._result: Optional[EntityID] = None
    # 避難所の周りの道路
    self._priority_roads = set()
    # 視界内の道路
    self._visible_roads: set[EntityID] = set()
    # 全ての土木隊のIDを取得
    self._superior_police_ids: list[EntityID] = []

    self._logger.info(
      f"Superior agents to avoid: {[pid.get_value() for pid in self._superior_police_ids]}"
    )

    # サブモジュールの取得
    # クラスタリング
    self._clustering: Clustering = cast(
      Clustering,
      module_manager.get_module(
        "Search.Clustering",
        "adf_core_python.implement.module.algorithm.k_means_clustering.KMeansClustering",
      ),
    )
    # 経路探索
    self._path_planning: PathPlanning = cast(
      PathPlanning,
      module_manager.get_module(
        "Search.PathPlanning",
        "adf_core_python.implement.module.algorithm.a_star_path_planning.AStarPathPlanning",
      ),
    )
    # ログの設定
    self._logger = get_agent_logger(
      f"{self.__class__.__module__}.{self.__class__.__qualname__}",
      self._agent_info,
    )

    self.register_sub_module(self._clustering)
    self.register_sub_module(self._path_planning)

  def update_info(self, message_manager: MessageManager) -> Search:
    super().update_info(message_manager)
    if self.get_count_update_info() > 1:
      # 視界内に入った道路をログに出力(debug)
      changed_entities = self._world_info.get_change_set()
      self._visible_roads = [
        entity_id
      for entity_id in changed_entities.get_changed_entities()
        if isinstance(self._world_info.get_entity(entity_id), Road)
    ]

      # 視界内の道路だった場合未探索リストから除外する
      for road_id in self._visible_roads:
        if road_id in self._unreached_road_ids:
          self._unreached_road_ids.discard(road_id)
      return self


    # 現在地の確認とリストの更新
    searched_road_id = self._agent_info.get_position_entity_id()
    # 建物の中にいる場合、その建物を探索済みにする
    if searched_road_id is not None:
      self._unreached_road_ids.discard(searched_road_id)

    # 探索リストが空になった場合、再取得
    if len(self._unreached_road_ids) == 0:
      self._unreached_road_ids = self._get_search_targets()

    # 最初の一回のみ優先道路を取得
    # if len(self._priority_roads) == 0:
    #   for entity in self._world_info.get_entities_of_types([Refuge]):# 避難所だけをentitiesに入れている
    #     if not isinstance(entity, Building):
    #       continue
    #     for entity_id in entity.get_neighbors():
    #       neighbor = self._world_info.get_entity(entity_id)
    #       if isinstance(neighbor, Road):
    #         self._priority_roads.add(entity_id)
    #   # 「優先道路を全部で50本見つけた」という初期化の結果
    #   self._logger.debug(f"priority_roads_registered: {[str(id) for id in self._priority_roads]}")



    #自分よりIDの小さい土木隊のIDを取得
    if len(self._superior_police_ids) == 0:
      all_police = sorted(
        self._world_info.get_entities_of_types([PoliceForce]),
        key=lambda police: police.get_entity_id().get_value(),
      )

      my_id = self._agent_info.get_entity_id()

      for police in all_police:
        police_id = police.get_entity_id()
        if police_id.get_value() < my_id.get_value():
          self._superior_police_ids.append(police_id)
        else:
          # IDは昇順なので、自分以降はチェック不要
          self._logger.debug(f"superior_police_id: {self._superior_police_ids}")
          break

    self._logger.debug(
      f"unreached_road_ids: {[str(id) for id in self._unreached_road_ids]}"
    )

    return self

  def calculate(self) -> Search:
    # 自分のクラスタを優先し，途中に優先道路があれば確認する
    target_road_id: Optional[EntityID] = None
    target_score: Optional[float] = None
    score: Optional[float] = None

    # 自身のクラスタIDを取得
    cluster_index: int = self._clustering.get_cluster_index(
      self._agent_info.get_entity_id()
    )

    self._logger.debug(f"befor score: {score}")
    # 行ってない道を調べる
    for road_id in self._unreached_road_ids:
      # 現在地から建物までの直線距離を取得
      distance = self._world_info.get_distance(
        self._agent_info.get_entity_id(), road_id
      )
      # seed = (road_id.get_value() + self._agent_info.get_entity_id().get_value()) % 100
      # random_bonus = seed * 0.1
      score = 100000 / (distance + 1)  # + random_bonus

      # 道が自分のクラスタと同じだった場合重みをプラス
      if self._clustering.get_cluster_index(road_id) == cluster_index:
        score = score * 100.0  # 100は仮定値

      # その道が優先道路なら優先度を上げる
      if road_id in self._priority_roads:
        score *= 50

 
      # #自分よりIDの小さい部隊がいた場合，スコアを下げる
      # repulsion_sum = 0.0
      # for police_id in self._superior_police_ids:
      #   police = self._world_info.get_entity(police_id)
      #   dis = self._world_info.get_distance(road_id, police)
      #   if dis < 100000:
      #     repulsion_sum += 100000000 / (dis + 1) ** 2
      #     # self._logger.debug(f"police_distance: {dis}")
      
      # score = score / (repulsion_sum + 1)
      # self._logger.debug(f"after score: {score}") 

      # scoreが大きいものにターゲットを更新
      if target_score is None or target_score < score:
        target_road_id = road_id
        target_score = score

    self._result = target_road_id
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

  # 決定したIDを渡す
  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result

  # ターゲットになる建物のリストをつくる
  def _get_search_targets(self) -> set[EntityID]:
    # 自分の担当クラスタの特定
    cluster_index: int = self._clustering.get_cluster_index(
      self._agent_info.get_entity_id()
    )
    # #クラスタ内のエンティティを取得
    # cluster_entities: list[Entity] = self._clustering.get_cluster_entities(
    #   cluster_index
    # )
    # #建物のリストの作成
    # building_entity_ids: list[EntityID] = [
    #   entity.get_entity_id()
    #   for entity in cluster_entities
    #   if isinstance(entity, Building) and not isinstance(entity, Refuge)
    # ]

    all_road = self._world_info.get_entities_of_types([Road])

    road_entity_ids: list[EntityID] = [
      entity.get_entity_id() for entity in all_road if not isinstance(entity, Refuge)
    ]

    return set(road_entity_ids)
