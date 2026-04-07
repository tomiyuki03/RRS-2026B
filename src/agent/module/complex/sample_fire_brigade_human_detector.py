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
    
        # すべてのCivilianを取得
        civilians: list[Entity] = self._world_info.get_entities_of_types([Civilian])

        # 最も優先度の高いCivilianを探す
        highest_priority_civilian: Optional[EntityID] = None
        highest_priority: Optional[float] = None

        for civilian in civilians:
            # civilianがCivilianクラスのインスタンスでない場合はスキップ
            if not isinstance(civilian, Civilian):
                continue

            # civilianのHPが0以下の場合はすでに死んでしまっているのでスキップ
            if civilian.get_hp() <= 0:
                continue

            # civilianの埋没度が0以下の場合は掘り起こす必要がないのでスキップ
            if civilian.get_buriedness() <= 0:
                continue

            # 距離を取得
            distance: float = self._world_info.get_distance(me, civilian.get_entity_id())
        
            # HPを取得
            hp: int = civilian.get_hp()
        
            # 優先度スコアを計算
            distance_km = distance / 1000.0
            priority = (1.0 / (distance_km / 100.0 + 1.0)) * (1.0 / (hp + 1.0))

            # 最も優先度の高いCivilianを更新
            if highest_priority is None or priority > highest_priority:
                highest_priority_civilian = civilian.get_entity_id()
                highest_priority = priority

        # 計算結果を格納
        self._result = highest_priority_civilian
    
        # ロガーに出力（優先度も表示）
        if highest_priority is not None:
            self._logger.info(f"Target: {self._result}, Priority: {highest_priority:.8f}")
        else:
            self._logger.info("No target found")

        # デバッグ：上位5件の要救助者の情報を出力
        if self._logger.isEnabledFor(logging.info):
         # 優先度順にソート
            priority_list = []
            for civilian in civilians:
                if not isinstance(civilian, Civilian):
                    continue
                if civilian.get_hp() <= 0 or civilian.get_buriedness() <= 0:
                    continue
        
            distance = self._world_info.get_distance(me, civilian.get_entity_id())
            hp = civilian.get_hp()
            distance_km = distance / 1000.0
            priority = (1.0 / (distance_km / 100.0 + 1.0)) * (1.0 / (hp + 1.0))
        
            priority_list.append({
                'id': civilian.get_entity_id(),
                'distance': distance,
                'hp': hp,
                'priority': priority
            })
    
        # 優先度の高い順にソート
        priority_list.sort(key=lambda x: x['priority'], reverse=True)
    
        # 上位5件を表示
        self._logger.info("=== Priority-sorted Targets ===")
        for i, item in enumerate(priority_list[:5]):
            self._logger.info(
                f"[{i+1}] ID:{item['id']} Distance:{item['distance']:.1f}mm "
                f"HP:{item['hp']} Priority:{item['priority']:.8f}"
            )

        return self

    def get_target_entity_id(self) -> Optional[EntityID]:
        """
        行動対象のEntityIDを取得する
        
        Returns
        -------
            Optional[EntityID]: 行動対象のEntityID
        """
        return self._result