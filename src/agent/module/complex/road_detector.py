from typing import Optional, cast

from rcrscore.entities import Building, EntityID, GasStation, Refuge, Road, PoliceForce, AmbulanceTeam, FireBrigade, Civilian

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
from adf_core_python.core.component.module.algorithm.clustering import Clustering
from src.agent.module.complex.police_search import PoliceSearch
from adf_core_python.core.component.module.complex.road_detector import RoadDetector
from rcrscore.urn import EntityURN

# 評価計算：重みまとめ
_WEIGHT_DISTANCE = 400.0
_WEIGHT_PRIORITY_ROAD = 500.0
_WEIGHT_POLICEFORCE = 2000.0
_WEIGHT_FIREBRIGADE = 3000.0
_WEIGHT_AMBULANCETEAM = 3000.0
_WEIGHT_CIVILIAN = 1000.0
_WEIGHT_REFUGE_DISTANCE = 1000.0
_WEIGHT_CLUSTERING = 3000.0
_PRIOLITY_MIN = float("-inf")

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

    #-------------サブモジュール登録-------------------
    # path_planningモジュールの設定
    self._path_planning: PathPlanning = cast(
      PathPlanning,
      module_manager.get_module(
        "RoadDetector.PathPlanning",
        "adf_core_python.implement.module.algorithm.a_star_path_planning.AStarPathPlanning",
      ),
    )
    self.register_sub_module(self._path_planning)

    # クラスタリングモジュールの設定
    self._clustering: Clustering = cast(
      Clustering,
      module_manager.get_module(
        "RoadDetector.Clustering",
        "adf_core_python.implement.module.algorithm.k_means_clustering.KMeansClustering",
      ),
    )
    self.register_sub_module(self._clustering)

    # searchモジュールの設定
    self._search: Search = cast(
       PoliceSearch,
       module_manager.get_module(
          "RoadDetector.PoliceSearch",
          "src.agent.module.complex.police_search.PoliceSearch"
       ),
    )
    self.register_sub_module(self._search)



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
    # entities = self._world_info.get_entities_of_types([Refuge, Building, GasStation])
    # for entity in entities:
    #   if not isinstance(entity, Building):
    #     continue
    #   for entity_id in entity.get_neighbors():
    #     neighbor = self._world_info.get_entity(entity_id)
    #     if isinstance(neighbor, Road):
    #       self._target_areas.add(entity_id)

    # 避難所の周りの道路を全て集める
    self._priority_roads = set()
    for entity in self._world_info.get_entities_of_types([Refuge]):# 避難所だけをentitiesに入れている
      if not isinstance(entity, Building):
        continue
      for entity_id in entity.get_neighbors():
        neighbor = self._world_info.get_entity(entity_id)
        if isinstance(neighbor, Road):
          self._priority_roads.add(entity_id)

    self._refuges = self._world_info.get_entities_of_types([Refuge])
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
    self._civilian = self._world_info.get_entities_of_types([Civilian])

    for road in self._world_info.get_entities_of_types([Road]):
      if road.get_blockades() is not None and len(road.get_blockades()) > 0:
        self._target_areas.add(road.get_entity_id())

    remove_list = []
    for target in self._target_areas:
      entity = self._world_info.get_entity(target)
      if isinstance(entity, Road):
        if entity.get_blockades() == []:
            remove_list.append(target)

    for r in remove_list:
      self._target_areas.discard(r)


    agent_pos = self._agent_info.get_position_entity_id()

    filtered = set()
    for t in self._target_areas:
      if self._world_info.get_distance(agent_pos, t) < 20000:
        filtered.add(t)
    self._target_areas = filtered


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
            self._target_areas.discard(self._result)
            self._result = None
    
    


    # 現在位置の取得
    agent_position = self._agent_info.get_position_entity_id()
    
    _best_refuge_distance = float("inf")
    _best_refuge = agent_position
    
    # 最も近い避難所の算出
    for entity in self._refuges:
      _distance = self._world_info.get_distance(entity.get_entity_id(), agent_position)
      if _best_refuge_distance > _distance:
        _best_refuge_distance = _distance
        _best_refuge = entity
    
    self._best_refuge = _best_refuge
    self._best_refuge_distance = _best_refuge_distance

    # 一番近い市民から最も近い避難所までの道を考える
    self._refuge_paths = []
   
    nearest = self._nearest_agent(self._civilian,self._best_refuge)

    if nearest is not None:
        start = self._agent_info.get_position_entity_id()
        if start is not None:
            path = self._path_planning.get_path(
                start,
                self._best_refuge.get_entity_id()
            )
            if path is not None:
                self._refuge_paths.append(set(path))


    return self

  def calculate(self) -> RoadDetector:
    self._police = self._world_info.get_entities_of_types([PoliceForce])
    self._fire = self._world_info.get_entities_of_types([FireBrigade])
    self._ambulance = self._world_info.get_entities_of_types([AmbulanceTeam])
    
    # 毎回再評価
    agent_position = self._agent_info.get_position_entity_id()
    if agent_position is None:
        return self

    _highest_target_area = agent_position
    _highest_evaluate = _PRIOLITY_MIN

    if len(self._target_areas) == 0:
      self._result = None
      return self
    
    for target_area in self._target_areas:
        score = self._evaluate(target_area)
        if score > _highest_evaluate:
            _highest_evaluate = score
            _highest_target_area = target_area

    if _highest_evaluate == _PRIOLITY_MIN:
        self._result = None
    else:
        path = self._path_planning.get_path(agent_position, _highest_target_area)
        if path is not None and len(path) > 0:
            self._result = path[-1]
    return self
  
  # 評価値計算
  def _evaluate(self,target_area :EntityID) -> float:
    return (
      self._score_distance(target_area) * _WEIGHT_DISTANCE
      + self._score_priority_road(target_area) * _WEIGHT_PRIORITY_ROAD
      + self._score_PoliceForce(target_area) * _WEIGHT_POLICEFORCE
      + self._score_FireBrigade(target_area) * _WEIGHT_FIREBRIGADE
      + self._score_AmbulanceTeam(target_area) * _WEIGHT_AMBULANCETEAM
      + self._score_civilians(target_area) * _WEIGHT_CIVILIAN
      + self._score_refuge_distance(target_area) * _WEIGHT_REFUGE_DISTANCE
      + self._score_clustering(target_area) * _WEIGHT_CLUSTERING
    )
  

  # 距離スコア：距離+1の逆数を返す(0除算対策)
  def _score_distance(self,target_area :EntityID) -> float:
    #現在位置の取得
    agent_position = self._agent_info.get_position_entity_id()
    # 現在位置の取得確認
    if agent_position is None:
      return float("-inf")
    
    return  1/((self._world_info.get_distance(agent_position, target_area)/1000)+1)
  
  # 優先道路スコア：優先道路に含まれているか
  def _score_priority_road(self,target_area:EntityID) -> float:
    return 1.0 if target_area in self._priority_roads else 0.0

  # 土木隊ペナルティスコア：他の土木隊がいるエリアは評価値を下げる
  # ターゲットエリアと自身以外の土木隊の中で一番ターゲットエリアに近いエージェントとの距離をみて，
  # 一定距離内にいるかつ自身のIDが奇数なら離れるようにする
  def _score_PoliceForce(self, target_area):

    _shortest_distance = float("inf")
    myself = self._agent_info.get_myself()
    if myself is None:
      return 0
    for pol in self._police:  
      # 自分はスルーされるように
      if pol.get_entity_id() == myself.get_entity_id():
        _distance = float("inf")
      else:
      
        _distance = self._world_info.get_distance(target_area,pol.get_position())

      if _shortest_distance > _distance:
        _shortest_distance  = _distance

    if _shortest_distance < 3000 :

      if myself.get_entity_id().get_value() % 2 == 0:
          return -300
      
      return 0
        
    elif _shortest_distance < 6000 :
      return -60
    
    return 0
  
  # 消防隊スコア：消防隊がいるエリアの評価値を上げる
  def _score_FireBrigade(self, target_area):
     return self._agent_erea_count(self._fire,target_area)
  
  # 救急隊スコア：救急隊がいるエリアの評価値を上げる
  def _score_AmbulanceTeam(self, target_area):
     return self._agent_erea_count(self._ambulance,target_area)
  
  # 市民スコア：市民がいるエリア(近隣の道も含む)の評価値を上げる
  def _score_civilians(self, target_area):
    score = 0

    for civ in self._civilian:
        pos = civ.get_position()
        if pos is None:
            continue

        entity = self._world_info.get_entity(pos)

        # 建物内だけ対象
        if entity is None:
          continue
        if entity.get_urn() != EntityURN.BUILDING:
          continue
       
        # 距離ベース
        d = self._world_info.get_distance(target_area, pos)
        score += 100 / (d + 1)

        for neighbor_id in entity.get_neighbors():
            if neighbor_id == target_area:
                score += 2.0 


    return score
  
 
  # 避難経路スコア：現在位置から避難所までの道に含まれている場合スコアを増やす
  def _score_refuge_distance(self,target_area):
      # 経路が存在するか確認
    for path_set in self._refuge_paths:
      if target_area in path_set:
        return 1.0
    return 0.0
  
  # クラスタリングスコア：クラスタリング内のエリアの評価値を上げる
  def _score_clustering(self,target_area):
    my_cluster = self._clustering.get_cluster_index(
       self._agent_info.get_myself().get_entity_id()
    )
    target_cluster = self._clustering.get_cluster_index(target_area)

    if my_cluster is None or target_cluster is None:
        return 0.0

    return 1.0 if target_cluster == my_cluster else -1.0
   # エリア内近隣にいるエージェントをカウントする
  def _agent_erea_count(self,agent,target_area):
    count = 0
    #_neighbor_road = set()
    #target_entity = self._world_info.get_entity(target_area)
    
    # # 近隣道路を集める
    # for entity_id in target_entity.get_neighbors():
    #     neighbor = self._world_info.get_entity(entity_id)
    #     if isinstance(neighbor, Road):
    #       _neighbor_road.add(entity_id)
    
    # # 該当種類のエージェントが近隣道路にいるなら+0.5,その場にいるなら+1
    # for age in agent:
    #   pos = age.get_position()
    #   if pos == target_area:
    #     count += 1
    #   if pos in _neighbor_road:
    #     count += 0.3
    for age in agent:
      d = self._world_info.get_distance(target_area,age.get_position())
      count += 100/(1+d)
    return count
  
  # 特定のエンティティと一番近い指定タイプのエージェントを返す
  def _nearest_agent(self, agents, area):
    _shortest_distance = float("inf")
    _near_age = None  

    my_pos = area.get_entity_id()
    if my_pos is None:
        return None

    for age in agents:
        pos = age.get_position()
        if pos is None:
            continue

        # とりあえず距離は必ず計算
        distance = self._world_info.get_distance(my_pos, pos)

        # Civilianの条件
        if isinstance(age, Civilian):
            position = self._world_info.get_entity(pos)
            if position is None:
                distance = float("inf")
            elif position.get_urn() != EntityURN.ROAD:
                distance = float("inf")

        # 比較
        if distance < _shortest_distance:
            _shortest_distance = distance
            _near_age = age

    return _near_age
 

  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result
