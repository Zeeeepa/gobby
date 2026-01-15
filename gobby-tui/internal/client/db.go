package client

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	_ "github.com/mattn/go-sqlite3"
)

type DBClient struct {
	db        *sql.DB
	ProjectID string
}

func NewDBClient() (*DBClient, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, err
	}
	dbPath := filepath.Join(home, ".gobby", "gobby-hub.db")

	// Open in RO mode if possible, but standard is fine since we are careful
	// Actually, simple Open is fine.
	db, err := sql.Open("sqlite3", dbPath)
	if err != nil {
		return nil, err
	}

	// Ping to verify
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("failed to connect to db at %s: %v", dbPath, err)
	}

	return &DBClient{
		db: db,
	}, nil
}

func (c *DBClient) Close() {
	if c.db != nil {
		c.db.Close()
	}
}

// ResolveProjectID finds the project ID and Name for the current working directory.
// It relies on the 'projects' table mapping paths to IDs.
func (c *DBClient) ResolveProjectID(cwd string) (string, string, error) {
	absPath, err := filepath.Abs(cwd)
	if err != nil {
		return "", "", err
	}

	rows, err := c.db.Query("SELECT id, name, repo_path FROM projects")
	if err != nil {
		return "", "", err
	}
	defer rows.Close()

	var bestMatchID, bestMatchName string
	var bestMatchLen int

	for rows.Next() {
		var id, name string
		var repoPath sql.NullString
		if err := rows.Scan(&id, &name, &repoPath); err != nil {
			continue
		}

		if !repoPath.Valid {
			continue
		}

		path := repoPath.String
		rel, err := filepath.Rel(path, absPath)
		if err != nil {
			continue
		}

		// If rel does not start with "..", it's inside
		if !strings.HasPrefix(rel, "..") {
			if len(path) > bestMatchLen {
				bestMatchLen = len(path)
				bestMatchID = id
				bestMatchName = name
			}
		}
	}

	if bestMatchID == "" {
		return "", "", fmt.Errorf("no project found for path: %s", cwd)
	}

	return bestMatchID, bestMatchName, nil
}

type Project struct {
	ID   string
	Name string
}

func (c *DBClient) ListProjects() ([]Project, error) {
	rows, err := c.db.Query("SELECT id, name FROM projects ORDER BY name")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var projects []Project
	for rows.Next() {
		var p Project
		if err := rows.Scan(&p.ID, &p.Name); err != nil {
			return nil, err
		}
		projects = append(projects, p)
	}
	return projects, nil
}

// TaskBrief is a minimal task representation for lists
type TaskBrief struct {
	ID        string
	Title     string
	Status    string
	Priority  int
	SeqNum    int
	ProjectID string
}

func (c *DBClient) ListTasks(projectID string, status string) ([]TaskBrief, error) {
	query := "SELECT id, title, status, priority, seq_num, project_id FROM tasks WHERE 1=1"
	var args []interface{}

	if projectID != "" {
		query += " AND project_id = ?"
		args = append(args, projectID)
	}

	if status != "" {
		query += " AND status = ?"
		args = append(args, status)
	}

	query += " ORDER BY priority ASC, created_at ASC"

	rows, err := c.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var tasks []TaskBrief
	for rows.Next() {
		var t TaskBrief
		var seqNum sql.NullInt64
		if err := rows.Scan(&t.ID, &t.Title, &t.Status, &t.Priority, &seqNum, &t.ProjectID); err != nil {
			return nil, err
		}
		if seqNum.Valid {
			t.SeqNum = int(seqNum.Int64)
		}
		tasks = append(tasks, t)
	}
	return tasks, nil
}

type SessionBrief struct {
	ID         string
	Status     string
	ExternalID string
	Source     string
	ProjectID  string
	UpdatedAt  string
}

func (c *DBClient) ListSessions(projectID string) ([]SessionBrief, error) {
	query := "SELECT id, status, external_id, source, project_id, updated_at FROM sessions WHERE 1=1"
	var args []interface{}

	if projectID != "" {
		query += " AND project_id = ?"
		args = append(args, projectID)
	}

	query += " ORDER BY updated_at DESC"

	rows, err := c.db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var sessions []SessionBrief
	for rows.Next() {
		var s SessionBrief
		var eid, src sql.NullString
		if err := rows.Scan(&s.ID, &s.Status, &eid, &src, &s.ProjectID, &s.UpdatedAt); err != nil {
			return nil, err
		}
		if eid.Valid {
			s.ExternalID = eid.String
		}
		if src.Valid {
			s.Source = src.String
		}
		sessions = append(sessions, s)
	}
	return sessions, nil
}
