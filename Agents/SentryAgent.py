import time
import json
import datetime
import Agents.Constants as Constants

from spade import agent, quit_spade
from spade.behaviour import OneShotBehaviour, CyclicBehaviour, PeriodicBehaviour
from spade.message import Message
from spade.template import Template


def processMeasurements(results):
    isFire = 0
    if results["temperature"] > Constants.TemperatureThreshold:
        isFire += 1
    if results["humidity"] < Constants.HumidityThreshold:
        isFire += 1
    if results["co2"] > Constants.Co2Threshold:
        isFire += 1
    if results["wind"] > Constants.WindThreshold:
        isFire += 1
    return isFire


class SentryAgent(agent.Agent):
    class MonitoringService(PeriodicBehaviour):
        async def run(self):
            request = Message(str(self.get("mySelf")))
            request.set_metadata("type", "measurementRequest")
            await self.send(request)
            if self.get('logging'):
                print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    checking measurements...")

    class ProcessingService(CyclicBehaviour):

        async def run(self):
            results = await self.receive(timeout=10 * Constants.MeasurementSecondsInterval)
            if results is None:
                if self.get('logging'):
                    print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    measurementRequest timeout - none arrived")
                # break/kill agent here?
            else:
                if processMeasurements(json.loads(results.body)) == 1:
                    # TODO
                    # call service, sensor damaged
                    if self.get('logging'):
                        print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    1 sensors discovered fire!")
                elif processMeasurements(json.loads(results.body)) == 2:
                    # TODO
                    # call service
                    self.agent.add_behaviour(self.agent.CheckNeighbours())
                    if self.get('logging'):
                        print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    2 sensors discovered fire!")
                elif processMeasurements(json.loads(results.body)) == 3:
                    self.agent.add_behaviour(self.agent.CheckNeighbours())
                    if self.get('logging'):
                        print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    3 sensors discovered fire!")
                elif processMeasurements(json.loads(results.body)) == 4:
                    # TODO
                    # call fire!
                    if self.get('logging'):
                        print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    4 sensors discovered fire!")

    class SendMeasurementsService(CyclicBehaviour):
        async def run(self):
            msg = await self.receive()
            if msg:
                if self.get('logging'):
                    print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    got request from: '{msg.sender}'")

                response = Message(to=str(msg.sender))
                if str(msg.sender) == self.get('mySelf'):
                    response.set_metadata("type", "measurementResponse") #response to itself
                else:
                    response.set_metadata("type", "neighborResponse") #response to neighbor request

                # TODO
                # some rest aip service here?

                if self.get('mySelf') == "sentry1@jabbers.one":
                    response.body = ' {"temperature": 90, "humidity": 9, "co2": 90, "wind": 90}'  # Set the fire ON message content
                else:
                    response.body = ' {"temperature": 20, "humidity": 20, "co2": 0.002, "wind": 20}'  # Set the fire OFF message content
                await self.send(response)

    class CheckNeighbours(OneShotBehaviour):
        async def run(self):
            if self.get('logging'):
                print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    checking neighbors")
            for neighbor in self.get('neighbors'):
                if self.get('logging'):
                    print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]          sending to: " + neighbor)
                msg = Message(to=neighbor)
                msg.set_metadata("type", "measurementRequest")
                await self.send(msg)

    class NeighbourResponseService(CyclicBehaviour):
        def __init__(self):
            super().__init__()
            self.neighborResults = []

        async def run(self):
            msg = await self.receive(timeout=100100100)  # wait infinite long
            if msg is not None:
                self.neighborResults.append(msg)
                if self.get('logging'):
                    print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    neighbor response: {msg.sender}")

                if len(self.get('neighbors')) == len(self.neighborResults):
                    if self.get('logging'):
                        print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    checking neighbor responses!")

                    positiveCount = 0
                    for result in self.neighborResults:
                        if processMeasurements(json.loads(result.body)) > 2:
                            positiveCount += 1

                    if self.get('logging'):
                        print(f"[{datetime.datetime.now().time()}]    [{self.get('mySelf')}]    positive (fire)/all results: {positiveCount}/{len(self.neighborResults)}")
                    self.neighborResults = []  # reset results

                    if positiveCount == 0:
                        msg = Message(to='camera1@jabbers.one')
                        msg.set_metadata("type", "faultySentry")
                        msg.body = self.get('mySelf')
                        await self.send(msg)
                    elif positiveCount == 1: # 1 positive result (from neighbor) fire or not? call camera
                        msg = Message(to='camera1@jabbers.one')
                        msg.set_metadata("type", "cameraRequest")
                        # TODO make coordinate parameter
                        msg.body = '1'
                        await self.send(msg)
                    elif positiveCount == 2: #2 positive results -> smal fire
                        msg = Message(to='extinguisher1@jabbers.one')
                        msg.set_metadata("type", "smallFire")
                        # TODO make coordinate parameter
                        msg.body = '1'
                        await self.send(msg)
                    else: #more than 2 positive results -> big fire
                        msg = Message(to='extinguisher1@jabbers.one')
                        msg.set_metadata("type", "callEmergency")
                        msg.body = self.get('mySelf')
                        await self.send(msg)

    async def setup(self):
        start_at = datetime.datetime.now() + datetime.timedelta(seconds=5)
        self.add_behaviour(self.MonitoringService(period=Constants.MeasurementSecondsInterval, start_at=start_at))

        template = Template()  # Respond to other Sentries with local measurements
        template.set_metadata("type", "measurementRequest")
        self.add_behaviour(self.SendMeasurementsService(), template)

        template = Template()  # Respond to origin sentry only measurementRequest
        template.set_metadata("type", "measurementResponse")
        self.add_behaviour(self.ProcessingService(), template)

        template = Template()  # Recieve responses from other agents to measurementRequest
        template.set_metadata("type", "neighborResponse")
        self.add_behaviour(self.NeighbourResponseService(), template)

        print(f"Agent {self.get('mySelf')} initialized")
