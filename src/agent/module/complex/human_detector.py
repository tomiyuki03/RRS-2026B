from typing import Optional, cast

from rcrscore.entities import Civilian, Entity, EntityID, Human
from rcrscore.urn import EntityURN

from adf_core_python.core.agent.develop.develop_data import DevelopData
from adf_core_python.core.agent.info.agent_info import AgentInfo
from adf_core_python.core.agent.info.scenario_info import ScenarioInfo
from adf_core_python.core.agent.info.world_info import WorldInfo
from adf_core_python.core.agent.module.module_manager import ModuleManager
from adf_core_python.core.component.module.algorithm.clustering import Clustering
from adf_core_python.core.component.module.complex.human_detector import HumanDetector
from adf_core_python.core.logger.logger import get_agent_logger

# HumanDetectorを継承したクラス
class SampleHumanDetector(HumanDetector):

  # 初期化
  def __init__(
    self,
    agent_info: AgentInfo,
    world_info: WorldInfo,
    scenario_info: ScenarioInfo,
    module_manager: ModuleManager,
    develop_data: DevelopData,
  ) -> None:
    
    # 親クラスの初期化
    super().__init__(
      agent_info, world_info, scenario_info, module_manager, develop_data
    )

    # クラスタリングモジュールの取得（エリア分割用）
    self._clustering: Clustering = cast(
      Clustering,
      module_manager.get_module(
        "SampleHumanDetector.Clustering",
        "adf_core_python.implement.module.algorithm.k_means_clustering.KMeansClustering",
      ),
    )

    # サブモジュールとして登録
    self.register_sub_module(self._clustering)

    # 現在のターゲット（救助対象）
    self._result: Optional[EntityID] = None

    # ロガーの生成
    self._logger = get_agent_logger(
      f"{self.__class__.__module__}.{self.__class__.__qualname__}",
      self._agent_info,
    )

  # 毎ステップ呼ばれる処理（ターゲット決定）
  def calculate(self) -> HumanDetector:

    self._logger.info("=== calculate start ===")

    # すでに誰かを搬送中ならその人をターゲットにする
    transport_human: Optional[Human] = self._agent_info.some_one_on_board()
    if transport_human is not None:
        self._result = transport_human.get_entity_id()
        self._logger.info(f"transporting human -> target = {self._result}")
        return self

    # 既にターゲットがある場合，まだ有効かチェック
    if self._result is not None:
        self._logger.info(f"current target = {self._result}")
        if not self._is_valid_human(self._result):
            self._logger.info(f"current target invalid -> reset target")
            self._result = None

    # ターゲットが無い場合，新しく選ぶ
    if self._result is None:
        self._logger.info("target is None -> select new target")
        self._result = self._select_target()

    self._logger.info(f"calculate result target = {self._result}")
    return self
  
  # ターゲットを選択する処理
  def _select_target(self) -> Optional[EntityID]:

    # 既存ターゲットが有効ならそのまま使用
    if self._result is not None and self._is_valid_human(self._result):
        self._logger.info(f"use current valid target = {self._result}")
        return self._result

    # 自分が属するクラスタ番号を取得
    cluster_index: int = self._clustering.get_cluster_index(
        self._agent_info.get_entity_id()
    )
    self._logger.info(f"cluster index = {cluster_index}")

    # クラスタ内のエンティティ取得
    cluster_entities: list[Entity] = self._clustering.get_cluster_entities(
        cluster_index
    )
    self._logger.info(f"cluster entities count = {len(cluster_entities)}")

    # クラスタ内で「有効な市民」のみ抽出
    cluster_valid_human_entities: list[Entity] = [
        entity
        for entity in cluster_entities
        if self._is_valid_human(entity.get_entity_id()) and isinstance(entity, Civilian)
    ]
    self._logger.info(f"cluster valid civilians count = {len(cluster_valid_human_entities)}")

    # クラスタ内に対象がいれば，priority が最も高い市民を選ぶ
    if len(cluster_valid_human_entities) != 0:
        highest_priority_entity = None
        highest_priority = None
        
        for entity in cluster_valid_human_entities:
            distance = self._world_info.get_distance(
                self._agent_info.get_entity_id(),
                entity.get_entity_id(),
            )
            hp = entity.get_hp()

            distance_score = 1.0 / (distance + 1.0)
            hp_score = 1.0 / (hp + 1.0)
            priority = distance_score + (5.0 * hp_score)
        
            self._logger.info(
                f"candidate from cluster -> id = {entity.get_entity_id()}," 
                f"distance = {distance}, hp = {hp}, priority = {priority}"
            )

            if highest_priority is None or priority > highest_priority:
                highest_priority = priority
                highest_priority_entity = entity

        selected_distance = self._world_info.get_distance(
            self._agent_info.get_entity_id(),
            highest_priority_entity.get_entity_id(),
        )

        selected_hp = highest_priority_entity.get_hp()

        self._logger.info(
                f"selected from cluster -> id = {highest_priority_entity.get_entity_id()}," 
                f"distance = {selected_distance}, hp = {selected_hp}, priority = {highest_priority}"
            )

        return highest_priority_entity.get_entity_id()
    
    # クラスタ内にいない場合，全体から探索
    world_valid_human_entities: list[Entity] = [
        entity
        for entity in self._world_info.get_entities_of_types([Civilian])
        if self._is_valid_human(entity.get_entity_id())
    ]
    self._logger.info(f"world valid civilians count = {len(world_valid_human_entities)}")

    # 全体から priority が最も高い市民を選択
    if len(world_valid_human_entities) != 0:
        highest_priority_entity = None
        highest_priority = None

        
        for entity in world_valid_human_entities:

            # 自分から有効な市民までの距離を取得
            distance = self._world_info.get_distance(
                self._agent_info.get_entity_id(),
                entity.get_entity_id(),
            )
            hp = entity.get_hp()

            distance_score = 1.0 / (distance + 1.0)
            hp_score = 1.0 / (hp + 1.0)
            priority = distance_score + (5.0 * hp_score)
        
            # 各候補の情報をログ出力
            self._logger.info(
                f"candidate from world -> id = {entity.get_entity_id()}," 
                f"distance = {distance}, hp = {hp}, priority = {priority}"
            )

            # 今までの最大priorityと比較し，より大きければ更新
            if highest_priority is None or priority > highest_priority:
                highest_priority = priority
                highest_priority_entity = entity

        selected_distance = self._world_info.get_distance(
            self._agent_info.get_entity_id(),
            highest_priority_entity.get_entity_id(),
        )
        
        selected_hp = highest_priority_entity.get_hp()

        # 最終的に選択された市民をログ出力
        self._logger.info(
                f"selected from world -> id = {highest_priority_entity.get_entity_id()}," 
                f"distance = {selected_distance}, hp = {selected_hp}, priority = {highest_priority}"
            )

        return highest_priority_entity.get_entity_id()

    self._logger.info("no valid target found")
    return None

  # 「救助対象として有効か」を判定する関数
  def _is_valid_human(self, target_entity_id: EntityID) -> bool:

    # エンティティ取得
    target: Optional[Entity] = self._world_info.get_entity(target_entity_id)
    if target is None:
        self._logger.info(f"{target_entity_id}: target is None")
        return False

    # Humanでなければ対象外
    if not isinstance(target, Human):
        self._logger.info(f"{target_entity_id}: not Human")
        return False

    # HPチェック（死んでいる場合は対象外）
    hp: Optional[int] = target.get_hp()
    if hp is None or hp <= 0:
        self._logger.info(f"{target_entity_id}: invalid hp = {hp}")
        return False

    # 埋没度チェック
    buriedness: Optional[int] = target.get_buriedness()
    if buriedness is None:
        self._logger.info(f"{target_entity_id}: buriedness is None")
        return False

    # 自分自身の情報取得
    myself = self._agent_info.get_myself()
    if myself is None:
        self._logger.info(f"{target_entity_id}: myself is None")
        return False

    # 消防隊：埋没していない人は対象外
    #if myself.get_urn() == EntityURN.FIRE_BRIGADE and buriedness == 0:
    #    self._logger.info(f"{target_entity_id}: fire brigade skips non-buried human")
    #    return False

    # 救急隊：埋没している人は対象外
    if myself.get_urn() == EntityURN.AMBULANCE_TEAM and buriedness > 0:
        self._logger.info(f"{target_entity_id}: ambulance team skips buried human (buriedness = {buriedness})")
        return False

    # ダメージがない（無傷）は対象外
    damage: Optional[int] = target.get_damage()
    if damage is None or damage == 0:
        return False

    # 位置取得
    position_entity_id: Optional[EntityID] = target.get_position()
    if position_entity_id is None:
        self._logger.info(f"{target_entity_id}: position_entity_id is None")
        return False

    position: Optional[Entity] = self._world_info.get_entity(position_entity_id)
    if position is None:
        self._logger.info(f"{target_entity_id}: position entity is None")
        return False

    # 避難所や救急隊の中にいる場合は対象外
    urn: EntityURN = position.get_urn()
    if urn == EntityURN.REFUGE:
        self._logger.info(f"{target_entity_id}: already in refuge")
        return False

    if urn == EntityURN.AMBULANCE_TEAM:
        self._logger.info(f"{target_entity_id}: already on ambulance team")
        return False

    self._logger.info(
        f"{target_entity_id}: valid target (hp = {hp}, buriedness = {buriedness}, position = {position_entity_id})"
    )
    return True


    

  # 現在のターゲットを返す
  def get_target_entity_id(self) -> Optional[EntityID]:
    return self._result

