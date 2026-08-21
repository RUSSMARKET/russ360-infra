package sqlite

import (
	"bytes"
	"strings"
	"testing"
)

func TestSanitizePipelinePreservesBackticksInsideGrafanaJSON(t *testing.T) {
	input := "INSERT INTO alert_rule VALUES(1,'{\"expr\":\"sum({app=~\\\"api\\\"} |~ `(?i)error` [5m])\"}');\n"
	columns := map[string][]string{"alert_rule": {"id", "data"}}
	var output bytes.Buffer

	if err := sanitizePipelineStream(strings.NewReader(input), &output, columns); err != nil {
		t.Fatal(err)
	}

	if !strings.Contains(output.String(), "`(?i)error`") {
		t.Fatalf("LogQL backticks were corrupted: %s", output.String())
	}
}
