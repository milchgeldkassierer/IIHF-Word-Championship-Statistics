from flask_sqlalchemy import SQLAlchemy
from dataclasses import dataclass, field

db = SQLAlchemy()

# --- Dataclass for Team Statistics ---
@dataclass
class TeamStats:
    name: str
    group: str
    gp: int = 0; w: int = 0; otw: int = 0; sow: int = 0
    l: int = 0; otl: int = 0; sol: int = 0
    gf: int = 0; ga: int = 0; pts: int = 0
    rank_in_group: int = 0 # Added for semifinal seeding

    @property
    def gd(self) -> int:
        return self.gf - self.ga

@dataclass
class TeamOverallStats:
    team_name: str
    team_iso_code: str | None
    gp: int = 0
    gf: int = 0
    ga: int = 0
    eng: int = 0  # Empty Net Goals scored by this team
    sog: int = 0  # Shots On Goal FOR this team
    soga: int = 0 # Shots On Goal AGAINST this team
    so: int = 0   # Shutouts achieved by this team
    ppgf: int = 0 # Powerplay Goals For
    ppga: int = 0 # Powerplay Goals Against (goals conceded while opponent was on PP)
    ppf: int = 0  # Powerplay Opportunities For (estimated)
    ppa: int = 0  # Powerplay Opportunities Against (times shorthanded - estimated)
    pim: int = 0  # Total Penalty Infraction Minutes for the team

@dataclass
class AllTimeTeamStats:
    team_code: str
    gp: int = 0
    w: int = 0
    otw: int = 0
    sow: int = 0
    l: int = 0
    otl: int = 0
    sol: int = 0
    gf: int = 0
    ga: int = 0
    pts: int = 0
    years_participated: set[int] = field(default_factory=set)

    @property
    def gd(self) -> int:
        return self.gf - self.ga

    @property
    def num_years_participated(self) -> int:
        return len(self.years_participated)

# --- Models ---
class ChampionshipYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    fixture_path = db.Column(db.String(300), nullable=True)
    games = db.relationship('Game', backref='championship_year', lazy=True, cascade="all, delete-orphan")
    def __repr__(self): return f'<ChampionshipYear {self.name} ({self.year})>'

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year_id = db.Column(db.Integer, db.ForeignKey('championship_year.id'), nullable=False)
    date = db.Column(db.String(20)); start_time = db.Column(db.String(20))
    round = db.Column(db.String(50)); group = db.Column(db.String(10), nullable=True)
    game_number = db.Column(db.Integer)
    team1_code = db.Column(db.String(3)); team2_code = db.Column(db.String(3))
    location = db.Column(db.String(100)); venue = db.Column(db.String(100))
    team1_score = db.Column(db.Integer, nullable=True); team2_score = db.Column(db.Integer, nullable=True)
    result_type = db.Column(db.String(10), nullable=True, default='REG')
    team1_points = db.Column(db.Integer, default=0); team2_points = db.Column(db.Integer, default=0)
    def __repr__(self): return f'<Game {self.game_number}: {self.team1_code} vs {self.team2_code}>'

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_code = db.Column(db.String(3), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    jersey_number = db.Column(db.Integer, nullable=True)
    def __repr__(self): return f'<Player {self.first_name} {self.last_name} (#{self.jersey_number} - {self.team_code})>'

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team_code = db.Column(db.String(3), nullable=False)
    minute = db.Column(db.String(5), nullable=False)
    goal_type = db.Column(db.String(10), nullable=False)
    is_empty_net = db.Column(db.Boolean, default=False, nullable=False)
    scorer_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    assist1_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    assist2_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    game = db.relationship('Game', backref=db.backref('goals', lazy='dynamic', cascade="all, delete-orphan"))
    scorer = db.relationship('Player', foreign_keys=[scorer_id], backref=db.backref('goals_scored', lazy=True))
    assist1 = db.relationship('Player', foreign_keys=[assist1_id], backref=db.backref('assists1', lazy=True))
    assist2 = db.relationship('Player', foreign_keys=[assist2_id], backref=db.backref('assists2', lazy=True))
    def __repr__(self): return f'<Goal by {self.scorer_id} in Game {self.game_id} at {self.minute}>'

class Penalty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team_code = db.Column(db.String(3), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    minute_of_game = db.Column(db.String(5), nullable=False)
    penalty_type = db.Column(db.String(10), nullable=False)
    reason = db.Column(db.String(100), nullable=False)
    game = db.relationship('Game', backref=db.backref('penalties', lazy='dynamic', cascade="all, delete-orphan"))
    player = db.relationship('Player', foreign_keys=[player_id], backref=db.backref('penalties_taken', lazy=True))
    def __repr__(self): return f'<Penalty {self.penalty_type} to {self.team_code} in Game {self.game_id} at {self.minute_of_game}>'

class ShotsOnGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team_code = db.Column(db.String(3), nullable=False)
    period = db.Column(db.Integer, nullable=False) # 1, 2, 3, 4 (OT)
    shots = db.Column(db.Integer, default=0, nullable=False)
    game = db.relationship('Game', backref=db.backref('sog_entries', lazy='dynamic', cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint('game_id', 'team_code', 'period', name='_game_team_period_uc'),)
    def __repr__(self): return f'<ShotsOnGoal Game {self.game_id} Team {self.team_code} P{self.period}: {self.shots}>'

# --- Dataclass for Game Display ---
@dataclass
class GameDisplay:
    id: int; year_id: int; date: str; start_time: str; round: str; group: str; game_number: int
    location: str; venue: str
    team1_code: str  # RESOLVED team code
    team2_code: str  # RESOLVED team code
    original_team1_code: str
    original_team2_code: str
    team1_score: int = None; team2_score: int = None
    result_type: str = None
    team1_points: int = 0; team2_points: int = 0
    sorted_events: list = field(default_factory=list)
    sog_data: dict = field(default_factory=dict) # {team_code: {period: shots}}
    scores_fully_match_goals: bool = False # Placeholder 