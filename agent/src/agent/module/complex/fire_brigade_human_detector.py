from typing import Optional, cast
import logging

from rcrscore.entities import Civilian, Entity, EntityID, Human, FireBrigade, PoliceForce, AmbulanceTeam
from rcrscore.urn import EntityURN

from adf_core_python.core.agent.develop.develop_data import DevelopData
from adf_core_python.core.agent.info.agent_info import AgentInfo
from adf_core_python.core.agent.info.scenario_info import ScenarioInfo
from adf_core_python.core.agent.info.world_info import WorldInfo
from adf_core_python.core.agent.module.module_manager import ModuleManager
from adf_core_python.core.component.module.algorithm.clustering import Clustering
from adf_core_python.core.component.module.complex.human_detector import HumanDetector
from adf_core_python.core.logger.logger import get_agent_logger

class FireBrigadeHumanDetector(HumanDetector):
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
        # 計算結果を格納する変数
        self._result: Optional[EntityID] = None
        # ロガーの取得
        self._logger = get_agent_logger(
            f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            self._agent_info,
        )

    def calculate(self) -> HumanDetector:
        """
        行動対象を決定する（優先度スコア版）

        Returns
        -------
            HumanDetector: 自身のインスタンス
        """
        # 自分自身のEntityIDを取得
        me: EntityID = self._agent_info.get_entity_id()
    
        # すべてのエンティティを取得
        police_forces: list[Entity] = self._world_info.get_entities_of_types([PoliceForce])
        fire_brigades: list[Entity] = self._world_info.get_entities_of_types([FireBrigade])
        ambulance_teams: list[Entity] = self._world_info.get_entities_of_types([AmbulanceTeam])
        civilians: list[Entity] = self._world_info.get_entities_of_types([Civilian])
        
        # 最も優先度の高い土木隊を探す
        self.log_priority_ranking(police_forces, PoliceForce, me, "PoliceForce")
        target = self.highest_priority_target(police_forces,PoliceForce,me)
        if target is not None:
            self._result = target
            return self
        
        # 最も優先度の高い消防隊を探す
        self.log_priority_ranking(fire_brigades, FireBrigade, me, "FireBrigade")
        target = self.highest_priority_target(fire_brigades,FireBrigade,me)
        if target is not None:
            self._result = target
            return self
        
        # 最も優先度の高い救急隊を探す
        self.log_priority_ranking(ambulance_teams, AmbulanceTeam, me, "AmbulanceTeam")
        target = self.highest_priority_target(ambulance_teams,AmbulanceTeam,me)
        if target is not None:
            self._result = target
            return self
        
        # 最も優先度の高い市民を探す
        self.log_priority_ranking(civilians, Civilian, me, "Civilian")
        target = self.highest_priority_target(civilians,Civilian,me)
        if target is not None:
            self._result = target
            return self
        
        # 何も見つからない場合
        self._result = None
        return self
        

    def get_target_entity_id(self) -> Optional[EntityID]:
        """
        行動対象のEntityIDを取得する
        
        Returns
        -------
            Optional[EntityID]: 行動対象のEntityID
        """
        return self._result
    
    def distance_hp(self, me: EntityID, target: Human) -> float:
        """
        優先度スコアを計算する
        """
        # 距離を取得
        distance: float = self._world_info.get_distance(me, target.get_entity_id())

        # HPを取得
        hp: int = target.get_hp()

        # 優先度スコアを計算
        distance_km = distance / 1000.0
        priority: float = (1.0 / (distance_km / 100.0 + 1.0)) * (1.0 / (hp + 1.0))

        return priority

    def highest_priority_target(self, targets: list[Entity],expected_type: type[Human],me: EntityID,) -> Optional[EntityID]:
        """
        指定された候補リストの中から,最も優先度の高い対象を1人選ぶ
        """
        highest_priority_target: Optional[EntityID] = None
        highest_priority: Optional[float] = None

        for target in targets:
            # 指定した型でなければスキップ
            if not isinstance(target, expected_type):
                continue

            # 自分自身ならスキップ
            if target.get_entity_id() == me:
                continue

            # 死亡しているならスキップ
            hp = target.get_hp()
            if hp is None or hp <= 0:
                continue

            # 埋没していないならスキップ
            buriedness = target.get_buriedness()
            if buriedness is None or buriedness <= 0:
                continue

            priority = self.distance_hp(me, target)

            # 最も優先度の高い対象を更新
            if highest_priority is None or priority > highest_priority:
                highest_priority_target = target.get_entity_id()
                highest_priority = priority

        return highest_priority_target
    
    def log_priority_ranking(self,targets,expected_type,me: EntityID,label: str) -> None:
        """
        指定された候補リストの中から,ログを出力
        """
        priority_list = []

        for target in targets:
            # 指定した型でなければスキップ
            if not isinstance(target, expected_type):
                continue

            # 自分自身ならスキップ
            if target.get_entity_id() == me:
                continue

            # 死亡しているならスキップ
            hp = target.get_hp()
            if hp is None or hp <= 0:
                continue

            # 埋没していないならスキップ
            buriedness = target.get_buriedness()
            if buriedness is None or buriedness <= 0:
                continue

            distance: float = self._world_info.get_distance(me, target.get_entity_id())
            hp: int = target.get_hp()
            priority: float = self.distance_hp(me, target)

            priority_list.append({
                "id": target.get_entity_id(),
                "distance": distance,
                "hp": hp,
                "buriedness": target.get_buriedness(),
                "priority": priority,
            })

        # 優先度の高い順にソート
        self._logger.info(f"=== {label} Priority-sorted Targets ===")

        if not priority_list:
            self._logger.info(f"No {label} target found")
            return

        priority_list.sort(key=lambda x: x["priority"], reverse=True)

        for i, item in enumerate(priority_list[:5]):
            self._logger.info(
                f"[{i+1}] ID:{item['id']} "
                f"Distance:{item['distance']:.1f}mm "
                f"HP:{item['hp']} "
                f"Buriedness:{item['buriedness']} "
                f"Priority:{item['priority']:.8f}"
            )

    # # ロガーに出力（優先度も表示）
    #     if highest_priority is not None:
    #         self._logger.info(f"Target: {self._result}, Priority: {highest_priority:.8f}")
    #     else:
    #         self._logger.info("No target found")
    #     priority_list = []
    #     # デバッグ：上位5件の要救助者の情報を出力
    #     if self._logger.isEnabledFor(logging.INFO):
    #      # 優先度順にソート
    #         for civilian in civilians:
    #             if not isinstance(civilian, Civilian):
    #                 continue
    #             if civilian.get_hp() <= 0 or civilian.get_buriedness() <= 0:
    #                 continue
    #             # 以下のインデントをforに合わせて変更
    #             distance = self._world_info.get_distance(me, civilian.get_entity_id())
    #             hp = civilian.get_hp()
    #             distance_km = distance / 1000.0
    #             priority = (1.0 / (distance_km / 100.0 + 1.0)) * (1.0 / (hp + 1.0))
            
    #             priority_list.append({
    #                 'id': civilian.get_entity_id(),
    #                 'distance': distance,
    #                 'hp': hp,
    #                 'priority': priority
    #             })
    
    #     # 優先度の高い順にソート
    #     priority_list.sort(key=lambda x: x['priority'], reverse=True)
    
    #     # 上位5件を表示
    #     self._logger.info("=== Priority-sorted Targets ===")
    #     for i, item in enumerate(priority_list[:5]):
    #         self._logger.info(
    #             f"[{i+1}] ID:{item['id']} Distance:{item['distance']:.1f}mm "
    #             f"HP:{item['hp']} Priority:{item['priority']:.8f}"
    #         )

    #     return self