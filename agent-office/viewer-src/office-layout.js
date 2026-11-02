// Shared by the 3D scene, roster paging and geometry checks.
const TEAM_ORDER = ['client', 'red', 'blue'];
const TEAM_ZONES = {
  client: { x: -11, name: 'CLIENTS', color: '#57dfc4', floor: '#123d3b', prefix: 'C' },
  red: { x: 0, name: 'RED TEAM', color: '#ff6b79', floor: '#402333', prefix: 'R' },
  blue: { x: 11, name: 'BLUE TEAM', color: '#6ea9ff', floor: '#1d3154', prefix: 'B' },
};
const SEAT_OPTIONS = [12, 24];
const DEFAULT_TEAM_SEATS = 12;
const MAX_TEAM_SEATS = 24;

function teamSeat(team, index) {
  const zone = TEAM_ZONES[team];
  if (!zone || !Number.isInteger(index) || index < 0 || index >= MAX_TEAM_SEATS) throw new Error('Invalid team seat');
  return { team, index, label: `${zone.prefix}${String(index + 1).padStart(2, '0')}`,
    x: zone.x + ((index % 4) - 1.5) * 2.2, z: -2.6 - Math.floor(index / 4) * 2.35,
    w: 1.5, sideX: zone.x - 4.7, hub: [zone.x - 4.7, 2.5] };
}

function rosterPage(world, team = 'all', page = 0, seats = DEFAULT_TEAM_SEATS) {
  const capacity = SEAT_OPTIONS.includes(seats) ? seats : DEFAULT_TEAM_SEATS;
  const teams = team === 'all' ? TEAM_ORDER : TEAM_ORDER.filter(t => t === team);
  const groups = Object.fromEntries(teams.map(t => [t, world.actors.filter(a => a.team === t)]));
  const pages = Math.max(1, ...teams.map(t => Math.ceil(groups[t].length / capacity)));
  const index = Math.max(0, Math.min(Number.isInteger(page) ? page : 0, pages - 1));
  const items = teams.flatMap(t => groups[t].slice(index * capacity, (index + 1) * capacity));
  return { items, page: index, pages, count: teams.reduce((n, t) => n + groups[t].length, 0), capacity };
}

module.exports = { TEAM_ORDER, TEAM_ZONES, SEAT_OPTIONS, DEFAULT_TEAM_SEATS, MAX_TEAM_SEATS, teamSeat, rosterPage };
