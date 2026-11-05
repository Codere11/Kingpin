"""THE NOTICE BOARD API: requests to the town process, results applied here."""
import nemesis


class BoardAPI:
    def __init__(self, player, inventory, work):
        self.player = player
        self.inventory = inventory
        self.work = work

    def hire(self, town, kind, cb) -> None:
        player = self.player

        def done(res):
            if res and res.get("hired"):
                player.job = res.get("job") or player.job
                player.wage = int(res.get("wage") or 0)
                player.farm_plot = res.get("farm_plot")
                if res.get("nation") is not None:
                    player.nation = res["nation"]
                player.settled_at = town
                player.village = town
                player._pay_day = -1
            cb(res)

        self.work.hire(town, kind, done)

    def sell(self, town, offers, cb) -> None:
        player = self.player
        inventory = self.inventory

        def done(res):
            if res and res.get("sold"):
                for item, n in (res.get("taken") or {}).items():
                    inventory.consume(item, int(n))
                    nemesis.note_offence_seen(player, "sold", item)
                if res.get("coin"):
                    inventory.add("coin", int(res["coin"]))
            cb(res)

        self.work.sell(town, offers, done)
