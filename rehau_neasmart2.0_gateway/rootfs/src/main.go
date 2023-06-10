package main

import (
	"encoding/binary"
	"fmt"
	"github.com/labstack/echo/v4"
	"math"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/labstack/echo/v4/middleware"
	"github.com/simonvetter/modbus"
)

const (
	NEASMART_BASE_SLAVE_ADDR          = 1200
	BASE_ZONE_ID                      = 100
	ZONE_SETPOINT_ADDR_OFFSET         = 1
	ZONE_TEMP_ADDR_OFFSET             = 2
	ZONE_RH_ADDR_OFFSET               = 10
	MIXEDGROUP_VALVE_OPENING_OFFSET   = 9
	MIXEDGROUP_PUMP_STATE_OFFSET      = 10
	MIXEDGROUP_FLOW_TEMP_OFFSET       = 11
	MIXEDGROUP_RETURN_TEMP_OFFSET     = 12
	OUTSIDE_TEMPERATURE_ADDR          = 7
	FILTERED_OUTSIDE_TEMPERATURE_ADDR = 8
	HINTS_PRESENT_ADDR                = 6
	WARNINGS_PRESENT_ADDR             = 5
	ERRORS_PRESENT_ADDR               = 3
	GLOBAL_OP_MODE_ADDR               = 1
	GLOBAL_OP_STATUS_ADDR             = 2
	DEHUMIDIFIERS_ADDR_OFFSET         = 21
	EXTRA_PUMPS_ADDR_OFFSET           = 30
)

type ZoneID struct {
	BaseID uint16 `param:"base_id"`
	ID     uint16 `param:"zone_id"`
}

type GenericID struct {
	ID uint16 `param:"id"`
}

type Zone struct {
	ID               uint16  `json:"id"`
	State            uint16  `json:"state"`
	Setpoint         float32 `json:"setpoint"`
	Temperature      float32 `json:"temperature"`
	RelativeHumidity uint16  `json:"relativeHumidity"`
}

type ZoneConfig struct {
	BaseID   uint16   `param:"base_id"`
	ID       uint16   `param:"zone_id"`
	State    *uint16  `json:"state"`
	Setpoint *float32 `json:"setpoint"`
}

type MixedGroup struct {
	ID                 uint16  `json:"id"`
	MixingValveOpening uint16  `json:"mixing_valve_opening"`
	PumpStatus         uint16  `json:"pump_status"`
	FlowTemperature    float32 `json:"flow_temperature"`
	ReturnTemperature  float32 `json:"return_temperature"`
}

type OutsideTemperature struct {
	OutsideTemperature         float32 `json:"outside_temperature"`
	FilteredOutsideTemperature float32 `json:"filtered_outside_temperature"`
}

type HintsWarningErrors struct {
	HintsPresent    bool `json:"hints_present"`
	WarningsPresent bool `json:"warnings_present"`
	ErrorsPresent   bool `json:"errors_present"`
}

type OperationMode struct {
	Mode uint16 `json:"mode"`
}

type OperationStatus struct {
	Status uint16 `json:"status"`
}

type Dehumidifier struct {
	DehumidifierStatus bool `json:"dehumidifier_status"`
}

type Pump struct {
	PumpStatus bool `json:"pump_status"`
}

type RehauNeaSmartHandler struct {
	lock sync.RWMutex

	readingRegs [65536]uint16 // used for reading climate status
	writingRegs [65536]uint16 // used for modifying climate status
	slave_id    uint8
}

func main() {
	var server *modbus.ModbusServer
	var err error
	var rehauHandler *RehauNeaSmartHandler

	rehauHandler = &RehauNeaSmartHandler{}
	rehauHandler.slave_id = 240

	server, err = modbus.NewServer(&modbus.ServerConfiguration{
		URL:        "tcp://0.0.0.0:502",
		Timeout:    30 * time.Second,
		MaxClients: 5,
	}, rehauHandler)
	if err != nil {
		fmt.Printf("failed to create server: %v\n", err)
		os.Exit(1)
	}

	err = server.Start()
	if err != nil {
		fmt.Printf("failed to start server: %v\n", err)
		os.Exit(1)
	}

	echoServer := echo.New()

	echoServer.Use(middleware.Logger())
	echoServer.Use(middleware.Recover())

	echoServer.GET("/zones/:base_id/:zone_id", rehauHandler.HandleGETZone)
	echoServer.GET("/mixedgroups/:id", rehauHandler.HandleGETMixedCircuit)
	echoServer.GET("/outsidetemperature", rehauHandler.HandleGETOutsideTemp)
	echoServer.GET("/mode", rehauHandler.HandleGETMode)
	echoServer.GET("/status", rehauHandler.HandleGETStatus)
	echoServer.GET("/dehumidifier/:id", rehauHandler.HandleGETDehumidifier)
	echoServer.GET("/pumps/:id", rehauHandler.HandleGETExtraPumps)

	echoServer.POST("/mode", rehauHandler.HandlePOSTMode)
	echoServer.POST("/status", rehauHandler.HandlePOSTStatus)
	echoServer.POST("/zones/:base_id/:zone_id", rehauHandler.HandlePOSTZone)

	echoServer.GET("/health", rehauHandler.HandleGETHealth)

	echoServer.Logger.Fatal(echoServer.Start(":8080"))

	return
}

func unpackDPT9001(i uint16) float32 {
	h, l := uint8(i>>8), uint8(i&0xff)

	m := int(h&7)<<8 | int(l)
	if h&128 == 128 {
		m -= 2048
	}

	e := (h >> 3) & 15

	f := 0.01 * float32(m) * float32(uint(1)<<e)

	return float32(math.Round(float64(f)*100) / 100)
}

func packDPT9001(f float32) uint16 {
	buffer := []byte{0, 0}

	if f > 670760.96 {
		f = 670760.96
	} else if f < -671088.64 {
		f = -671088.64
	}

	signedMantissa := int(f * 100)
	exp := 0

	for signedMantissa > 2047 || signedMantissa < -2048 {
		signedMantissa /= 2
		exp++
	}

	buffer[0] |= uint8(exp&15) << 3

	if signedMantissa < 0 {
		signedMantissa += 2048
		buffer[0] |= 1 << 7
	}

	mantissa := uint(signedMantissa)

	buffer[0] |= uint8(mantissa>>8) & 7
	buffer[1] |= uint8(mantissa)

	return binary.BigEndian.Uint16(buffer)
}

func (rehauHandler *RehauNeaSmartHandler) HandleCoils(req *modbus.CoilsRequest) (res []bool, err error) {
	err = modbus.ErrIllegalFunction

	return
}

func (rehauHandler *RehauNeaSmartHandler) HandleDiscreteInputs(req *modbus.DiscreteInputsRequest) (res []bool, err error) {
	err = modbus.ErrIllegalFunction

	return
}

func (rehauHandler *RehauNeaSmartHandler) HandleHoldingRegisters(req *modbus.HoldingRegistersRequest) (res []uint16, err error) {
	var regAddr uint16

	if req.UnitId != 0 && req.UnitId != rehauHandler.slave_id {
		return
	}

	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	for i := 0; i < int(req.Quantity); i++ {
		regAddr = req.Addr + uint16(i)
		if req.IsWrite {
			rehauHandler.readingRegs[regAddr] = req.Args[i]
			res = append(res, rehauHandler.readingRegs[regAddr])
		} else {
			res = append(res, rehauHandler.writingRegs[regAddr])
		}
	}
	return
}

func (rehauHandler *RehauNeaSmartHandler) HandleInputRegisters(req *modbus.InputRegistersRequest) (res []uint16, err error) {
	err = modbus.ErrIllegalFunction

	return
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETZone(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	var zone ZoneID
	err := c.Bind(&zone)
	if err != nil {
		return c.String(http.StatusBadRequest, "bad request")
	}
	if zone.BaseID > 4 || zone.BaseID < 1 || zone.ID > 12 || zone.ID == 0 {
		return c.String(http.StatusBadRequest, "bad request")
	}

	zoneAddr := (zone.BaseID-1)*NEASMART_BASE_SLAVE_ADDR + zone.ID*BASE_ZONE_ID

	state := rehauHandler.readingRegs[zoneAddr]
	dpt9Setpoint := unpackDPT9001(rehauHandler.readingRegs[zoneAddr+ZONE_SETPOINT_ADDR_OFFSET])
	dpt9Temp := unpackDPT9001(rehauHandler.readingRegs[zoneAddr+ZONE_TEMP_ADDR_OFFSET])
	rh := rehauHandler.readingRegs[zoneAddr+ZONE_RH_ADDR_OFFSET]

	return c.JSON(http.StatusOK, Zone{
		State:            state,
		Setpoint:         dpt9Setpoint,
		Temperature:      dpt9Temp,
		RelativeHumidity: rh,
	})
}

func (rehauHandler *RehauNeaSmartHandler) HandlePOSTZone(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	var zoneConfig ZoneConfig
	err := c.Bind(&zoneConfig)
	if err != nil {
		return c.String(http.StatusBadRequest, "bad request")
	}

	zoneAddr := (zoneConfig.BaseID-1)*NEASMART_BASE_SLAVE_ADDR + zoneConfig.ID*BASE_ZONE_ID

	if zoneConfig.State != nil {
		if *zoneConfig.State == 0 || *zoneConfig.State > 6 {
			return c.String(http.StatusBadRequest, "bad request")
		}
		rehauHandler.writingRegs[zoneAddr] = *zoneConfig.State
	}
	if zoneConfig.Setpoint != nil {
		rehauHandler.writingRegs[zoneAddr+ZONE_SETPOINT_ADDR_OFFSET] = packDPT9001(*zoneConfig.Setpoint)
	}

	return c.NoContent(http.StatusAccepted)
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETMixedCircuit(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	var mixg GenericID
	err := c.Bind(&mixg)
	if err != nil {
		return c.String(http.StatusBadRequest, "bad request")
	}
	if mixg.ID == 0 || mixg.ID > 3 {
		return c.String(http.StatusBadRequest, "bad request")
	}

	mixingValveOpening := rehauHandler.readingRegs[mixg.ID+MIXEDGROUP_VALVE_OPENING_OFFSET]
	pumpStatus := rehauHandler.readingRegs[mixg.ID+MIXEDGROUP_PUMP_STATE_OFFSET]
	flowTemperature := unpackDPT9001(rehauHandler.readingRegs[mixg.ID+MIXEDGROUP_FLOW_TEMP_OFFSET])
	returnTemperature := unpackDPT9001(rehauHandler.readingRegs[mixg.ID+MIXEDGROUP_RETURN_TEMP_OFFSET])

	return c.JSON(http.StatusOK, MixedGroup{
		MixingValveOpening: mixingValveOpening,
		PumpStatus:         pumpStatus,
		FlowTemperature:    flowTemperature,
		ReturnTemperature:  returnTemperature,
	})
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETOutsideTemp(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	outsideTemperature := unpackDPT9001(rehauHandler.readingRegs[OUTSIDE_TEMPERATURE_ADDR])
	filteredOutsideTemperature := unpackDPT9001(rehauHandler.readingRegs[FILTERED_OUTSIDE_TEMPERATURE_ADDR])

	return c.JSON(http.StatusOK, OutsideTemperature{
		OutsideTemperature:         outsideTemperature,
		FilteredOutsideTemperature: filteredOutsideTemperature,
	})
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETHintsWarningsErrors(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	hintsPresent := rehauHandler.readingRegs[HINTS_PRESENT_ADDR] != 0
	warningPresent := rehauHandler.readingRegs[WARNINGS_PRESENT_ADDR] != 0
	errorsPresent := rehauHandler.readingRegs[ERRORS_PRESENT_ADDR] != 0

	return c.JSON(http.StatusOK, HintsWarningErrors{
		HintsPresent:    hintsPresent,
		WarningsPresent: warningPresent,
		ErrorsPresent:   errorsPresent,
	})
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETMode(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	mode := rehauHandler.readingRegs[GLOBAL_OP_MODE_ADDR]

	return c.JSON(http.StatusOK, OperationMode{
		Mode: mode,
	})
}

func (rehauHandler *RehauNeaSmartHandler) HandlePOSTMode(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	var operationalMode OperationMode
	err := c.Bind(&operationalMode)
	if err != nil {
		return c.String(http.StatusBadRequest, "bad request")
	}
	if operationalMode.Mode == 0 || operationalMode.Mode > 5 {
		return c.String(http.StatusBadRequest, "bad request")
	}

	rehauHandler.writingRegs[GLOBAL_OP_MODE_ADDR] = operationalMode.Mode

	return c.NoContent(http.StatusAccepted)
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETStatus(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	status := rehauHandler.readingRegs[GLOBAL_OP_STATUS_ADDR]

	return c.JSON(http.StatusOK, OperationStatus{
		Status: status,
	})
}

func (rehauHandler *RehauNeaSmartHandler) HandlePOSTStatus(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	var operationalStatus OperationStatus
	err := c.Bind(&operationalStatus)
	if err != nil {
		return c.String(http.StatusBadRequest, "bad request")
	}
	if operationalStatus.Status == 0 || operationalStatus.Status > 6 {
		return c.String(http.StatusBadRequest, "bad request")
	}

	rehauHandler.writingRegs[GLOBAL_OP_STATUS_ADDR] = operationalStatus.Status

	return c.NoContent(http.StatusAccepted)
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETDehumidifier(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	var dehumidifierID GenericID
	err := c.Bind(&dehumidifierID)
	if err != nil {
		return c.String(http.StatusBadRequest, "bad request")
	}
	if dehumidifierID.ID == 0 || dehumidifierID.ID > 9 {
		return c.String(http.StatusBadRequest, "bad request")
	}

	dehumidifierStatus := rehauHandler.readingRegs[dehumidifierID.ID+DEHUMIDIFIERS_ADDR_OFFSET] != 0

	return c.JSON(http.StatusOK, Dehumidifier{
		DehumidifierStatus: dehumidifierStatus,
	})
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETExtraPumps(c echo.Context) error {
	rehauHandler.lock.Lock()
	defer rehauHandler.lock.Unlock()

	var pumpID GenericID
	err := c.Bind(&pumpID)
	if err != nil {
		return c.String(http.StatusBadRequest, "bad request")
	}
	if pumpID.ID == 0 || pumpID.ID > 5 {
		return c.String(http.StatusBadRequest, "bad request")
	}

	pumpStatus := rehauHandler.readingRegs[pumpID.ID+EXTRA_PUMPS_ADDR_OFFSET] != 0

	return c.JSON(http.StatusOK, Pump{
		PumpStatus: pumpStatus,
	})
}

func (rehauHandler *RehauNeaSmartHandler) HandleGETHealth(c echo.Context) error {
	return c.String(http.StatusOK, "OK")
}
