from typing import Optional, cast

import math

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
    self._superior_police_ids:set[EntityID] = set()
    #自分のクラスタから近い順にクラスタを保持
    self._cluster_priority_list:list[int] = list()


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

      return self

    # 現在地の確認とリストの更新
    searched_road_id = self._agent_info.get_position_entity_id()
    # 道路上にいる場合、その道路を探索済みにする
    if searched_road_id is not None:
      self._unreached_road_ids.discard(searched_road_id)

    # 探索リストが空になった場合、再取得
    if len(self._unreached_road_ids) == 0:
      self._unreached_road_ids = self._get_search_targets()

    #視界内の道路を判定済みにし，探索リストを更新する
    self._update_unreached_roads()

    #最初の一回のみ優先道路を取得
    if len(self._priority_roads) == 0:
      for entity in self._world_info.get_entities_of_types([Refuge]):# 避難所だけをentitiesに入れている
        if not isinstance(entity, Building):
          continue
        for entity_id in entity.get_neighbors():
          neighbor = self._world_info.get_entity(entity_id)
          if isinstance(neighbor, Road):
            self._priority_roads.add(entity_id)
      # 「優先道路を全部で50本見つけた」という初期化の結果
      self._logger.debug(f"priority_roads_registered: {[str(id) for id in self._priority_roads]}")

    #自分よりIDの小さい土木隊のIDを取得
    if not self._superior_police_ids:
      self._update_superior_police_ids()
    #if not self._cluster_priority_list:
     # self._init_cluster_priority()
       
    return self

  def calculate(self) -> Search:
    self._logger.debug(f"[{self._agent_info.get_time()}]police search calculate")
    # 自分のクラスタを優先し，途中に優先道路があれば確認する
    target_road_id: Optional[EntityID] = None
    target_score: Optional[float] = None
    score: Optional[float] = None

    # 自身のクラスタIDを取得
    cluster_index: int = self._clustering.get_cluster_index(
      self._agent_info.get_entity_id()
    )

    # 行ってない道を調べる
    for road_id in self._unreached_road_ids:
      #現在地から建物までの直線距離を取得
      distance = self._world_info.get_distance(
        self._agent_info.get_entity_id(), road_id
      )
      # seed = (road_id.get_value() + self._agent_info.get_entity_id().get_value()) % 100
      # random_bonus = seed * 0.1
      score = 100000 / (distance + 1)  # + random_bonus

      # 道が自分のクラスタと同じだった場合重みをプラス
      if self._clustering.get_cluster_index(road_id) == cluster_index:
        score = score * 1000.0  # 100は仮定値

      # その道が優先道路なら優先度を上げる
      if road_id in self._priority_roads:
        score *= 50

      # #自分よりIDの小さい部隊がいた場合，スコアを下げる
      #repulsion_sum = 0.0
      for police_id in self._superior_police_ids:
        if self._world_info.get_entity(police_id) is None:
          continue
        try:
          dis = self._world_info.get_distance(road_id, police_id)
          if dis < 50000:
            #repulsion_sum += 10000000000 / (dis + 1) ** 2
            score = 0.0
            break
        except Exception as e:
          # 万が一エラーが出ても、ここで止まらないようにする
          self._logger.error(f"Distance calculation error: {e}")
          continue

      if target_score is None or target_score < score:
        target_road_id = road_id
        target_score = score

    self._result = target_road_id
    return self

  # 決定したIDを渡す
  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result

  # ターゲットになる道路のリストをつくる
  def _get_search_targets(self) -> set[EntityID]:

    all_roads = self._world_info.get_entities_of_types([Road])

    road_entity_ids: list[EntityID] = [
      entity.get_entity_id()
      for entity in all_roads
      if isinstance(entity, Road)
    ]
    return set(road_entity_ids)
  
  #見探索リストの更新
  def _update_unreached_roads(self) -> None:
    # 視界内に入った道路
    changed_entities = self._world_info.get_change_set()
    self._visible_roads = [
      entity_id
      for entity_id in changed_entities.get_changed_entities()
      if isinstance(self._world_info.get_entity(entity_id), Road)
    ]
    self._logger.debug(
      f"[{self._agent_info.get_time()}] _visible_roads: {[str(id) for id in self._visible_roads]}"
    ) 

    # 視界内の道路だった場合未探索リストから除外する
    for road_id in self._visible_roads:
      if road_id in self._unreached_road_ids:
        self._unreached_road_ids.discard(road_id)
    self._logger.debug(
      f"[{self._agent_info.get_time()}] unreached_road_ids: {[str(id) for id in self._unreached_road_ids]}"
    ) 

 #自分よりIDの小さい土木隊を取得
  def _update_superior_police_ids(self) -> None:
    all_police = self._world_info.get_entities_of_types([PoliceForce])
        
      # 自分以外のエージェントが同期されるまで待つ
    if len(all_police) > 1:
      my_id = self._agent_info.get_entity_id()
        
      for police in all_police:            
        police_id = police.get_entity_id()
        # 自分より ID が小さいエージェントだけをセットに追加
        if police_id.get_value() < my_id.get_value():
          self._superior_police_ids.add(police_id)
          
      if self._superior_police_ids:
        self._logger.info(f"Fixed superior_ids (set): {self._superior_police_ids}")

  # def _init_cluster_priority(self):
  #   my_cluster_index: int = self._clustering.get_cluster_index(
  #     self._agent_info.get_entity_id()
  #   )
  #   my_center = self._clustering.get_cluster_center(my_cluster_index)

  #   dis_list = []
  #   num_clusters = self._clustering.get_num_cluster()

  #   for num in range(num_clusters):
  #     if num == my_cluster_index:
  #       continue
  #     target_center = self._clustering.get_cluster_center(num)
  #     distance = self._world_info.get_distance(my_center.get_x(), my_center.get_y(), target_center.get_x(), target_center.get_y())
  #     dis_list.append((num, distance))

  #   dis_list.sort(key=lambda x: x[1])
  #   self._cluster_priority_list = [item[0] for item in dis_list]

  #   self._logger.debug(f"priority_clusters: {[str(id) for id in self._cluster_priority_list]}")