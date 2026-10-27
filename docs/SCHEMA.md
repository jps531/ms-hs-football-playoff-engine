# Schema Diagram

`schools`, `games`, and `locations` each have an `overrides` JSONB column and a matching
`*_effective` view (`schools_effective`, `games_effective`, `locations_effective`) that merges
the override over the raw column. All reads (API and pipeline) go through the `*_effective`
views; all writes go to the base tables, and `overrides` is never written by the pipeline —
only via the admin override endpoints. See [API_REFERENCE.md](API_REFERENCE.md#admin--admin).

```mermaid
erDiagram
    schools {
        text school PK
        text city
        text zip
        real latitude
        real longitude
        text mascot
        text primary_color
        text secondary_color
        text primary_color_hex
        text secondary_color_hex
        text logo_primary
        text logo_secondary
        text logo_tertiary
        jsonb color_variants
        jsonb overrides
    }
    team_logos {
        int id PK
        text school FK
        text logo_type
        text image_url
        int year_start
        int year_end
        boolean is_primary
        boolean has_keyline
        text notes
        int source_submission_id FK
        timestamptz created_at
        timestamptz updated_at
    }
    helmet_designs {
        int id PK
        text school FK
        int year_first_worn
        int year_last_worn
        jsonb years_worn
        text image_left
        text image_right
        text photo
        text color
        text finish
        text facemask_color
        text logo
        text stripe
        text tags
        text notes
        boolean is_primary
        timestamptz created_at
    }
    school_seasons {
        text school PK,FK
        int season PK
        int class
        int region
        boolean is_active
    }
    locations {
        int id PK
        text name
        text city
        text home_team
        real latitude
        real longitude
        jsonb overrides
    }
    games {
        text school PK,FK
        date date PK
        text location
        int location_id FK
        text opponent
        int points_for
        int points_against
        text result
        boolean final
        text game_status
        int game_quarter
        text game_clock
        text source
        boolean region_game
        int season FK
        text round
        timestamptz kickoff_time
        int overtime
        jsonb overrides
        int helmet_design_id FK
    }
    region_standings {
        text school FK
        int season FK
        date as_of_date
        int class
        int region
        int wins
        int losses
        int ties
        int region_wins
        int region_losses
        int region_ties
        double odds_1st
        double odds_2nd
        double odds_3rd
        double odds_4th
        double odds_1st_weighted
        double odds_2nd_weighted
        double odds_3rd_weighted
        double odds_4th_weighted
        double odds_playoffs
        boolean clinched
        boolean eliminated
        boolean coin_flip_needed
        double odds_second_round "advancement odds; second_round unweighted/weighted pair repeats for quarterfinals, semifinals, finals, champion"
        double odds_quarterfinals
        double odds_semifinals
        double odds_finals
        double odds_champion
        double odds_playoffs_weighted
        double odds_second_round_weighted
        double odds_quarterfinals_weighted
        double odds_semifinals_weighted
        double odds_finals_weighted
        double odds_champion_weighted
        double odds_first_round_home "P(hosts round | reaches round); unweighted/weighted pair repeats for second_round, quarterfinals, semifinals"
        double odds_second_round_home
        double odds_quarterfinals_home
        double odds_semifinals_home
        double odds_first_round_home_weighted
        double odds_second_round_home_weighted
        double odds_quarterfinals_home_weighted
        double odds_semifinals_home_weighted
        timestamptz computed_at
        text model_version
    }
    region_standings_archive {
        bigint id PK
        text school
        int season
        date as_of_date
        int class
        int region
        timestamptz computed_at
        text model_version
        timestamptz archived_at
        jsonb snapshot "the whole region_standings row as written"
    }
    team_ratings {
        text school PK,FK
        int season PK
        date as_of_date PK
        real elo
        real rpi
        int games_played
        timestamptz computed_at
    }
    region_scenarios {
        int season PK
        varchar class PK
        int region PK
        date as_of_date PK
        timestamptz computed_at
        jsonb remaining_games
        jsonb scenario_atoms
        jsonb complete_scenarios
        jsonb key_insights
    }
    region_computation_state {
        int season PK
        int class PK
        int region PK
        date as_of_date PK
        int r_remaining
        boolean margin_sensitive
        text margin_compute_status
        timestamptz computed_at
        timestamptz margin_computed_at
    }
    region_seed_pairs {
        int season PK
        int class PK
        int region PK
        date as_of_date PK
        jsonb pairs
        jsonb pairs_weighted
        timestamptz computed_at
    }
    playoff_formats {
        int id PK
        int season
        int class
        int num_regions
        int seeds_per_region
        int num_rounds
        text notes
    }
    playoff_format_slots {
        int format_id PK,FK
        int slot PK
        int home_region
        int home_seed
        int away_region
        int away_seed
        text north_south
    }
    championship_venues {
        int season PK
        int class PK
        int location_id FK
    }

    submissions {
        int id PK
        text type
        text status
        text school FK
        int user_id FK
        jsonb payload
        text moderator_notes
        timestamptz reviewed_at
        timestamptz submitted_at
        timestamptz updated_at
        int helmet_design_id FK
    }
    users {
        int id PK
        text auth0_id
        text email
        text display_name
        text phone
        text hometown
        text role
        text favorite_team FK
        bool is_active
        timestamptz created_at
        timestamptz updated_at
    }
    user_followed_teams {
        int user_id PK,FK
        text school PK,FK
        timestamptz followed_at
    }
    user_attended_games {
        int user_id PK,FK
        text school PK,FK
        date date PK
        timestamptz attended_at
    }

    schools ||--o{ school_seasons : "plays in"
    schools ||--o{ helmet_designs : "wears"
    schools ||--o{ team_logos : "uses"
    submissions ||--o{ team_logos : "cut from"
    region_standings ||--o{ region_standings_archive : "every write copied to"
    schools ||--o{ team_ratings : "rated in"
    schools ||--o{ submissions : "submitted for"
    schools ||--o{ user_followed_teams : "followed by"
    users ||--o{ submissions : "submitted by"
    users ||--o{ user_followed_teams : "follows"
    users ||--o{ user_attended_games : "attended"
    games ||--o{ user_attended_games : "attended by"
    school_seasons ||--o{ games : "plays"
    school_seasons ||--o{ region_standings : "has odds in"
    locations ||--o{ games : "hosted at"
    helmet_designs ||--o{ games : "worn in"
    helmet_designs ||--o{ submissions : "linked from"
    playoff_formats ||--o{ playoff_format_slots : "has slots"
    locations ||--o{ championship_venues : "hosts"
```
