# -- coding: utf-8 --
# meulegado.py - Módulo para a aba "Meu Legado" do AnkiChat (v1.1 - Adiciona Separadores)

from aqt.qt import QWidget, QVBoxLayout, QTextBrowser

class LegacyTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.legacy_area = QTextBrowser()
        self.legacy_area.setReadOnly(True)
        self.legacy_area.setOpenExternalLinks(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.legacy_area)
        self.setLayout(layout)

    def update_display(self, legacy_data):
        """Recebe os dados do legado e atualiza a exibição na tela."""
        self.legacy_area.clear()
        self.legacy_area.append("<b>--- Meu Histórico de Temporadas ---</b><br>")
        if not legacy_data:
            self.legacy_area.append("<i>Você ainda não completou nenhuma temporada.</i>")
            return
        
        legacy_list = list(legacy_data.values())
        
        sorted_seasons = sorted(legacy_list, key=lambda item: int(item.get('season_key', '0_0').split('_')[0]), reverse=True)
        
        for data in sorted_seasons:
            season_key = data.get("season_key", "0_0")
            try:
                season_number, season_day = season_key.split('_')
                season_str = f"Temporada {season_number}"
            except (ValueError, IndexError):
                season_str = season_key.replace("_", " - Dia ")

            medal_map = {"gold": "🥇", "silver": "🥈", "bronze": "🥉"}
            medal_icon = medal_map.get(data.get("medal"), "")
            
            position_text = data.get('position', 'N/A')
            position_str = f"{position_text}º lugar" if isinstance(position_text, int) else position_text
            
            division_str = data.get('division', 'N/A')

            line = (f"<b>{season_str}:</b> {position_str} - Divisão {division_str} {medal_icon}<br>"
                    f"<small>  Pontos de Retenção: {data.get('retention_points', 0)} | Pontos de Meta: {data.get('meta_points', 0)}</small>")
            
            self.legacy_area.append(line)
            
            # Adiciona uma linha horizontal após cada entrada, exceto a última.
            if data != sorted_seasons[-1]:
                self.legacy_area.append("<hr>")